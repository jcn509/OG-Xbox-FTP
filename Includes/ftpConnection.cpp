#include <array>
#include <iostream>
#include <iomanip>
#include <string>
#include <algorithm>
#include <map>
#include "outputLine.h"
#include "ftpServer.h"
#include <assert.h>

#ifdef NXDK
#include <lwip/opt.h>
#include <lwip/arch.h>
#include <lwip/netdb.h>
#include <lwip/errno.h>
#include <lwip/sockets.h>
#include <lwip/debug.h>
#include <lwip/dhcp.h>
#include <lwip/init.h>
#include <lwip/netif.h>
#include <lwip/sys.h>
#include <lwip/tcpip.h>
#include <lwip/timeouts.h>
#include <netif/etharp.h>
#include <pktdrv.h>
#include <windows.h> // Used for file I/O
#include <nxdk/mount.h>
#include <xboxkrnl/xboxkrnl.h>
#else
#include <stdio.h>
#include <stdlib.h>
#include <cstring>
#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>

namespace
{
  bool nxIsDriveMounted(char) { return true; }
} // namespace
#endif

namespace
{
  // Set buffer sizes to 1KiB for commands and 64KiB for data
  // Command buffer should selldom (never?) exceed 512B but I prefer a little headroom.
  // Data buffer is bigger in order for disk writes to be quicker - writing bigger
  // chunks is usually preferable for a myriad of reasons.
  constexpr size_t k_ftp_cmd_buffer_size = 1024;
  constexpr size_t k_ftp_data_buffer_size = 64 * 1024;

  const std::array<const char, 8> k_drives{'C', 'D', 'E', 'F', 'G', 'X', 'Y', 'Z'};

  const std::array<const std::string, 4> k_types{
      "ASCII",
      "EBCDIC",
      "IMAGE",
      "LOCAL"};

  constexpr char k_reply_please_login[] = "220 Please enter your login name now.\r\n";
  constexpr char k_reply_password_required[] = "331 Password required.\r\n";
  constexpr char k_reply_user_logged_in[] = "230 User logged in, proceed.\r\n";
  constexpr char k_reply_format_current_directory_pwd[] = "257 \"%s\" is current directory\r\n";
  constexpr char k_reply_not_implemented[] = "502 %s not implemented.\r\n";
  constexpr char k_reply_format_type_set_to[] = "200 Type set to %s\r\n";
  constexpr char k_reply_format_current_directory_cwd[] = "250 \"%s\" is current directory.\r\n";
  constexpr char k_reply_unix_type_l8[] = "215 UNIX type: L8\r\n";
  constexpr char k_reply_port_command_ok[] = "200 Port command ok.\r\n";
  constexpr char k_reply_opening_ascii_data_connection_for_ls[] = "150 Opening ASCII data connection for ls\r\n";
  constexpr char k_reply_data_transfer_finished_successfully[] = "226 Data transfer finished successfully. Data connection closed.\r\n";
  constexpr char k_reply_command_parameter_not_implemented[] = "504 Command parameter not implemented.\r\n";
  constexpr char k_reply_file_action_ok[] = "250 Requested file action ok.\r\n";
  constexpr char k_reply_action_not_taken[] = "553 Requested action not taken.\r\n";
  constexpr char k_reply_not_logged_in[] = "530 Not logged in.\r\n";
} // namespace

void ftpConnection::sendStdString(std::string const &s, int flags = 0)
{
  sendStdString(_fd, s, flags);
}

void ftpConnection::sendStdString(int fd, std::string const &s, int flags = 0)
{
  send(fd, s.c_str(), s.length(), flags);
}

ftpConnection::ftpConnection(int fd, ftpServer *s) : buf(new char[k_ftp_cmd_buffer_size]), // Unfortunately make_unique doesn't seem to exist in the NXDK
                                                     _fd(fd), server(s)
{
  pwd = "/";
  logged_in = false;
  sendStdString(k_reply_please_login);
  mode = 'I';
}

ftpConnection::~ftpConnection()
{
  server = nullptr;
}

bool ftpConnection::update(void)
{
  // Might as well kill the connection if buffer memory allocation failed.
  if (!buf)
  {
    return false;
  }
  // handle data from a client
  int nbytes;
  if ((nbytes = recv(_fd, buf.get(), k_ftp_cmd_buffer_size, 0)) <= 0)
  {
    // got error or connection closed by client
    if (nbytes == 0)
    {
      // connection closed
    }
    else
    {
      outputLine("Error: recv\n");
    }
    /* Report back to server that we're a dud! */
    return false;
  }
  else
  {
    // We received a command!

    /* Add a terminating zero to the received string as the
     * client does not necessarily do so. */
    buf[nbytes] = '\0';

    /* Do what the command asks of you:
     *
     *   ABOR - abort a file transfer
     * / CWD  - change working directory (Lacks sanity check)
     * X CDUP - Move up to parent directory
     * X DELE - delete a remote file
     * X LIST - list remote files
     *   MDTM - return the modification time of a file
     * X MKD  - make a remote directory
     * X NLST - name list of remote directory
     * X PASS - send password
     *   PASV - enter passive mode
     * X PORT - open a data port
     * X EPRT - Extended data port (IPv6)
     * X PWD  - print working directory
     *   QUIT - terminate the connection
     * X RETR - retrieve a remote file
     * X RMD  - remove a remote directory
     * X RNFR - rename from
     * X RNTO - rename to
     *   SITE - site-specific commands
     *   SIZE - return the size of a file
     * X STOR - store a file on the remote host
     * X SYST - Identify yourself
     * / TYPE - set transfer type (Only accepts IMAGE and ASCII)
     * X USER - send username
     **/
    std::string recvdata(buf.get());
    size_t cmdDataSep = recvdata.find(' ', 0);
    std::string arg = " ";
    if (cmdDataSep == std::string::npos)
    {
      cmdDataSep = recvdata.find('\r', 0);
    }
    else
    {
      arg = recvdata.substr(cmdDataSep + 1, recvdata.find('\r') - (cmdDataSep + 1));
    }
    std::string cmd = recvdata.substr(0, cmdDataSep);

    if (!cmd.compare("USER"))
    {
      cmdUser(arg);
    }
    else if (!cmd.compare("PASS"))
    {
      cmdPass(arg);
    }
    else if (!cmd.compare("AUTH"))
    {
      cmdUnimplemented(cmd);
    }
    else if (logged_in)
    {
      if (!cmd.compare("ABOR"))
      {
        // cmdAbor();
        cmdUnimplemented(cmd);
      }
      else if (!cmd.compare("CWD"))
      {
        cmdCwd(arg);
      }
      else if (!cmd.compare("CDUP"))
      {
        cmdCdup();
      }
      else if (!cmd.compare("DELE"))
      {
        cmdDele(arg);
      }
      else if (!cmd.compare("LIST"))
      {
        cmdList(arg);
      }
      else if (!cmd.compare("MDTM"))
      {
        // cmdMdtm(arg);
        cmdUnimplemented(cmd);
      }
      else if (!cmd.compare("MKD"))
      {
        cmdMkd(arg);
      }
      else if (!cmd.compare("NLST"))
      {
        cmdNlst(arg);
      }
      else if (!cmd.compare("PASV"))
      {
        cmdUnimplemented(cmd);
      }
      else if (!cmd.compare("PORT"))
      {
        cmdPort(arg);
      }
      else if (!cmd.compare("EPRT"))
      {
        cmdEprt(arg);
      }
      else if (!cmd.compare("PWD"))
      {
        cmdPwd();
      }
      else if (!cmd.compare("QUIT"))
      {
        // cmdQuit();
        cmdUnimplemented(cmd);
      }
      else if (!cmd.compare("RETR"))
      {
        cmdRetr(arg);
      }
      else if (!cmd.compare("RMD"))
      {
        cmdRmd(arg);
      }
      else if (!cmd.compare("RNFR"))
      {
        cmdRnfr(arg);
      }
      else if (!cmd.compare("RNTO"))
      {
        cmdRnto(arg);
      }
      else if (!cmd.compare("SITE"))
      {
        // cmdSite(arg);
        cmdUnimplemented(cmd);
      }
      else if (!cmd.compare("SIZE"))
      {
        // cmdSize(arg);
        cmdUnimplemented(cmd);
      }
      else if (!cmd.compare("STOR"))
      {
        cmdStor(arg);
      }
      else if (!cmd.compare("SYST"))
      {
        cmdSyst();
      }
      else if (!cmd.compare("TYPE"))
      {
        cmdType(arg);
      }
      else
      {
        outputLine(("Received cmd " + cmd + ", arg " + arg + "\n").c_str());
        cmdUnimplemented(cmd);
      }
    }
    else
    {
      sendStdString(k_reply_not_logged_in);
    }
  }
  /* Tell the server that we're still alive and kicking! */
  return true;
}

void ftpConnection::cmdUser(std::string const &arg)
{
  if (!arg.compare(server->conf->getUser()))
  {
    sendStdString(k_reply_password_required);
  }
  else
  {
    sendStdString("530 login authentication failed.\r\n");
  }
}

void ftpConnection::cmdPass(std::string const &arg)
{
  if (!arg.compare(server->conf->getPassword()))
  {
    sendStdString(k_reply_user_logged_in);
    logged_in = true;
  }
  else
  {
    sendStdString("530 login authentication failed.\r\n");
  }
}

void ftpConnection::cmdPwd(void)
{
  sprintf(buf.get(), k_reply_format_current_directory_pwd, pwd.c_str());
  sendStdString(buf.get());
}

void ftpConnection::cmdType(std::string const &arg)
{
  if (arg[0] == 'I')
  {
    sprintf(buf.get(), k_reply_format_type_set_to, "IMAGE");
    sendStdString(buf.get());
    mode = 'I';
  }
  else if (arg[0] == 'A')
  {
    sprintf(buf.get(), k_reply_format_type_set_to, "ASCII");
    sendStdString(buf.get());
    mode = 'A';
  }
  else
  {
    sendStdString(k_reply_command_parameter_not_implemented);
  }
}

void ftpConnection::cmdCwd(std::string const &arg)
{
  std::string tmpPwd = "";
  if (arg[0] == '.' && arg[1] == '.')
  {
    tmpPwd = pwd.substr(0, pwd.rfind('/', pwd.rfind('/') - 1) + 1);
  }
  else if (arg[0] == '/')
  {
    if (arg.length() > 1)
    {
      tmpPwd = arg + "/";
    }
    else
    {
      tmpPwd = "/";
    }
  }
  else
  {
    tmpPwd = pwd + arg + "/";
  }
#ifdef NXDK
  if (tmpPwd.length() > 1)
  {
    std::string tmpDosPwd = unixToDosPath(tmpPwd);
    HANDLE soughtFolder;
    if ((soughtFolder = CreateFileA(tmpDosPwd.c_str(), GENERIC_READ, 0, NULL,
                                    OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL)) != INVALID_HANDLE_VALUE)
    {
      pwd = tmpPwd;
      sprintf(buf.get(), k_reply_format_current_directory_cwd, pwd.c_str());
      sendStdString(buf.get());
    }
    else
    {
      sendStdString(k_reply_not_logged_in);
    }
    CloseHandle(soughtFolder);
  }
  else
  {
    pwd = "/";
    sprintf(buf.get(), k_reply_format_current_directory_cwd, pwd.c_str());
    sendStdString(buf.get());
  }
#else
  pwd = tmpPwd;
  sprintf(buf.get(), k_reply_format_current_directory_cwd, pwd.c_str());
  sendStdString(buf.get());
#endif
}

void ftpConnection::cmdDele(std::string const &arg)
{
  std::string filename = arg;
  if (arg[0] != '/')
  {
    filename = pwd + arg;
  }
#ifdef NXDK
  filename = unixToDosPath(filename);
  if (DeleteFile(filename.c_str()))
  {
    sendStdString(k_reply_file_action_ok);
  }
  else
  {
    sendStdString(k_reply_action_not_taken);
  }
#else
  cmdUnimplemented("DELE");
#endif
}

void ftpConnection::cmdCdup(void)
{
  cmdCwd("..");
}

void ftpConnection::cmdSyst(void)
{
  sendStdString(k_reply_unix_type_l8);
}

void ftpConnection::cmdPort(std::string const &arg)
{
  int valueSep = arg.find(',', 0);
  valueSep = arg.find(',', valueSep + 1);
  valueSep = arg.find(',', valueSep + 1);
  valueSep = arg.find(',', valueSep + 1);
  std::string address = arg.substr(0, valueSep);
  std::replace(address.begin(), address.end(), ',', '.');

  int cmdDataSep = valueSep + 1;
  valueSep = arg.find(',', cmdDataSep);
  std::string p1 = arg.substr(cmdDataSep, valueSep - cmdDataSep);
  cmdDataSep = valueSep + 1;
  std::string p2 = arg.substr(cmdDataSep, std::string::npos);

  std::string port = std::to_string(stoi(p1) * 256 + stoi(p2));
  outputLine((address + " " + port + " " + std::to_string(_fd) + "\n").c_str());
  dataFd = server->openConnection(address, port);
  if (dataFd != -1)
  {
    sendStdString(k_reply_port_command_ok);
  }
  else
  {
    sendStdString("425 Socket creation failed.");
  }
}

void ftpConnection::cmdMkd(std::string const &arg)
{
#ifdef NXDK
  std::string filename = arg;
  if (arg[0] != '/')
  {
    filename = pwd + arg;
  }
  filename = unixToDosPath(filename);
  if (CreateDirectoryA(filename.c_str(), NULL))
  {
    sendStdString(k_reply_file_action_ok);
  }
  else
  {
    sendStdString(k_reply_action_not_taken);
  }
#else
  cmdUnimplemented("MKD");
#endif
}

void ftpConnection::cmdRmd(std::string const &arg)
{
#ifdef NXDK
  std::string filename = arg;
  if (arg[0] != '/')
  {
    filename = pwd + arg;
  }
  filename = unixToDosPath(filename);
  if (RemoveDirectoryA(filename.c_str()))
  {
    outputLine("Deleted directory: '%s'\n", filename.c_str());
    sendStdString(k_reply_file_action_ok);
  }
  else
  {
    outputLine("Failed to delete directory: '%s'\n", filename.c_str());
    sendStdString(k_reply_action_not_taken);
  }
#else
  cmdUnimplemented("RMD");
#endif
}

void ftpConnection::cmdRnfr(std::string const &arg)
{
#ifdef NXDK
  if (arg[0] != '/')
  {
    rnfr = pwd + arg;
  }
  else
  {
    rnfr = arg;
  }
  rnfr = unixToDosPath(rnfr);
  sendStdString("350 File action pending further information.\r\n");
#else
  cmdUnimplemented("RNFR");
#endif
}

void ftpConnection::cmdRnto(std::string const &arg)
{
  std::string filename = arg;
  if (arg[0] != '/')
  {
    filename = pwd + arg;
  }
  filename = unixToDosPath(filename);
  outputLine("Moving: '%s' to '%s'\n", rnfr.c_str(), filename.c_str());
#ifdef NXDK
  if (MoveFileA(rnfr.c_str(), filename.c_str()))
  {
    sendStdString(k_reply_file_action_ok);
  }
  else
  {
    sendStdString(k_reply_action_not_taken);
  }
  rnfr = "";
#else
  cmdUnimplemented("RNTO");
#endif
}

void ftpConnection::cmdList(std::string const &arg)
{
  if (dataFd != -1)
  {
    const std::string &path = (arg.empty() || arg == " ") ? pwd : arg;
    sendStdString(k_reply_opening_ascii_data_connection_for_ls);
    sendFolderContents(dataFd, path);
    close(dataFd);
    sendStdString(k_reply_data_transfer_finished_successfully);
  }
}

void ftpConnection::cmdNlst(std::string const &arg)
{
  if (dataFd != -1)
  {
    const std::string &path = (arg.empty() || arg == " ") ? pwd : arg;
    outputLine("arg: '%s'", arg.c_str());
    outputLine(" pwd: '%s'", pwd.c_str());
    sendStdString(k_reply_opening_ascii_data_connection_for_ls);
    sendFolderContents(dataFd, path, true);
    close(dataFd);
    sendStdString(k_reply_data_transfer_finished_successfully);
  }
}

void ftpConnection::cmdEprt(std::string const &arg)
{
  int family = std::stoi(arg.substr(1, 1));
  if (family != 1 && family != 2)
  {
    sendStdString("502 Unknown address family; use (1,2)\r\n");
    return;
  }
  char delimiter = arg[0];
  int portDelimiter = arg.find(delimiter, 3);
  std::string address = arg.substr(3, arg.find(delimiter, portDelimiter) - 3);
  ++portDelimiter;
  std::string port = arg.substr(portDelimiter,
                                arg.find(delimiter, portDelimiter) -
                                    portDelimiter);
  dataFd = server->openConnection(address, port);
  if (dataFd != -1)
  {
    sendStdString(k_reply_port_command_ok);
  }
  else
  {
    sendStdString("425 Socket creation failed.");
  }
}

void ftpConnection::cmdRetr(std::string const &arg)
{
  if (dataFd != -1)
  {
    std::string filename = arg;
    if (arg[0] != '/')
    {
      filename = pwd + arg;
    }
    outputLine("Trying to send file %s!\n", filename.c_str());
    sendStdString("150 Sending file " + arg + "\r\n");
    sendFile(filename);
    close(dataFd);
    sendStdString(k_reply_data_transfer_finished_successfully);
  }
}

void ftpConnection::cmdStor(std::string const &arg)
{
  if (dataFd != -1)
  {
    std::string filename = arg;
    if (arg[0] != '/')
    {
      filename = pwd + arg;
    }
    outputLine("Trying to receive file %s!\n", filename.c_str());
    sendStdString("150 Receiving file " + arg + "\r\n");
    recvFile(filename);
    close(dataFd);
    sendStdString(k_reply_data_transfer_finished_successfully);
  }
}

void ftpConnection::cmdUnimplemented(std::string const &arg)
{
  sprintf(buf.get(), k_reply_not_implemented, arg.c_str());
  sendStdString(buf.get());
}

std::string ftpConnection::unixToDosPath(std::string const &path)
{
  std::string ret;
  if (path[0] == '/' && path[1] == '/')
  {
    ret = path.substr(1, std::string::npos);
  }
  else
  {
    ret = path;
  }
  ret = ret.substr(1, 1) + ":" + path.substr(2, std::string::npos);
  std::replace(ret.begin(), ret.end(), '/', '\\');
  return ret;
}

void ftpConnection::sendFolderContents(int fd, const std::string &path, bool just_files)
{
  const std::string path_to_search = (path[0] == '/' && path[1] == '/') ? path.substr(1, std::string::npos) : path;
  if (!path_to_search.compare("/"))
  {
    for (const auto drive : k_drives)
    {
      if (nxIsDriveMounted(drive))
      {
        const std::string preamble = just_files ? "" : "drwxr-xr-x 1 XBOX XBOX 0 2020-03-02 10:41 ";
        sendStdString(fd, preamble + drive + "\r\n");
      }
    }
    return;
  }
#ifdef NXDK
  WIN32_FIND_DATAA fData;
  std::string searchmask = unixToDosPath(path_to_search + "*");
  outputLine("path: '%s' path_to_search:'%s' searchmask: '%s'\n", path.c_str(), path_to_search.c_str(), searchmask.c_str());
  HANDLE fHandle = FindFirstFileA(searchmask.c_str(), &fData);
  if (fHandle == INVALID_HANDLE_VALUE)
  {
    return;
  }
  do
  {
    std::string retstr = "";
    if (just_files)
    {
      retstr = std::string(fData.cFileName) + "\r\n";
    }
    else
    {
      if (fData.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
      {
        retstr = "d";
      }
      else
      {
        retstr = "-";
      }
      TIME_FIELDS fTime;
      RtlTimeToTimeFields((PLARGE_INTEGER)&fData.ftLastWriteTime, &fTime);
      retstr += "rwxr-xr-x 1 XBOX XBOX " +
                std::to_string(fData.nFileSizeLow) + " " +
                std::to_string(fTime.Year) + "-" + std::to_string(fTime.Month) + "-" + std::to_string(fTime.Day) + " " +
                std::to_string(fTime.Hour) + ":" + std::to_string(fTime.Minute) + " " +
                fData.cFileName + "\r\n";
    }
    sendStdString(fd, retstr);
  } while (FindNextFile(fHandle, &fData) != 0);
  FindClose(fHandle);
#else
  for (int q = 0; q < 10; ++q)
  {
    std::string retstr = (just_files ? std::to_string(q) : ("drwxr-xr-x 1 XBOX XBOX " + std::to_string(q) + " May 11 10:41 " + std::to_string(q))) + "\r\n";
    sendStdString(fd, retstr);
  }
  if (!just_files)
  {
    std::string retstr = "-rwxr-xr-x 1 XBOX XBOX 1024 May 11 10:41 X\r\n";
    sendStdString(fd, retstr);
  }
#endif
}

bool ftpConnection::sendFile(std::string const &filename)
{
#ifdef NXDK
  std::string filePath = unixToDosPath(filename);
  HANDLE fHandle = CreateFile(filePath.c_str(), GENERIC_READ, FILE_SHARE_READ,
                              NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
  outputLine(("\n" + filePath + "\n").c_str());
  if (fHandle == INVALID_HANDLE_VALUE)
  {
    outputLine("File opening failed. LOL.\n");
    return false;
  }
  const std::unique_ptr<unsigned char[]> sendBuffer(new unsigned char[k_ftp_data_buffer_size]);
  if (!sendBuffer)
  {
    outputLine("File sending buffer memory allocation failed.\n");
    return false;
  }
  int bytesToRead = k_ftp_data_buffer_size;
  unsigned long bytesRead = 0;
  if (mode == 'I')
  {
    while (ReadFile(fHandle, sendBuffer.get(), bytesToRead, &bytesRead, NULL) && (bytesRead > 0))
    {
      send(dataFd, sendBuffer.get(), bytesRead, 0);
    }
  }
  else if (mode == 'A')
  {
    std::string abuf;
    while (ReadFile(fHandle, sendBuffer.get(), bytesToRead, &bytesRead, NULL) && (bytesRead > 0))
    {
      abuf = reinterpret_cast<char *>(sendBuffer.get());
      std::for_each(abuf.begin(), abuf.begin() + bytesRead, [](char &c) { c &= 0x7F; });
      send(dataFd, abuf.c_str(), bytesRead, 0);
    }
  }
  CloseHandle(fHandle);
  return true;
#else
  char trash[1024];
  int bytesRead = 1024;
  send(dataFd, trash, bytesRead, 0);
  return true;
#endif
}

bool ftpConnection::recvFile(std::string const &filename)
{
  bool retVal = true;
  std::string filePath = unixToDosPath(filename);
#ifdef NXDK
  HANDLE fHandle = CreateFile(filePath.c_str(), GENERIC_WRITE,
                              0, NULL, CREATE_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL, NULL);
  if (fHandle == INVALID_HANDLE_VALUE)
  {
    outputLine("File creation failed. LOL. \n");
    return false;
  }
#endif
  const std::unique_ptr<unsigned char[]> recvBuffer(new unsigned char[k_ftp_data_buffer_size]);
  if (!recvBuffer)
  {
    outputLine("Could not create buffer for file receiving! \n");
    return false;
  }
  outputLine(("\r\n" + filePath + "\r\n").c_str());
  unsigned long bytesWritten;
  ssize_t bytesRead;
  while ((bytesRead = recv(dataFd, recvBuffer.get(), k_ftp_data_buffer_size, 0)))
  {
    if (bytesRead == -1)
    {
      outputLine("Error %d, aborting!\n", errno);
      retVal = false;
      break;
    }
#ifdef NXDK
    WriteFile(fHandle, recvBuffer.get(), bytesRead, &bytesWritten, NULL);
    if (bytesWritten != bytesRead)
    {
      outputLine("ERROR: Bytes read != Bytes written (%d, %d)\n", bytesRead, bytesWritten);
      retVal = false;
    }
#endif
  }
#ifdef NXDK
  CloseHandle(fHandle);
#endif
  return retVal;
}
