#ifndef CONFIG_HPP
#define CONFIG_HPP

#include <string>

class ftpConfig
{
  bool enable;
  std::string username;
  std::string password;
  int port;

public:
  ftpConfig();

  bool getEnabled() const { return enable; }
  const std::string &getUser() const { return username; }
  const std::string &getPassword() const { return password; }
  int getPort() const { return port; }

  void setEnabled(bool val);
  void setUser(std::string const &username);
  void setPassword(std::string const &password);
  void setPort(int port);
};

#endif