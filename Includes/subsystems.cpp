#include "subsystems.h"

#include "outputLine.h"

#ifdef NXDK
#include <nxdk/mount.h>
#include <nxdk/path.h>
#endif

#ifdef NXDK
#include "networking.h"

void mountHomeDir(const char Letter)
{
  char targetPath[MAX_PATH];
  char *finalSeparator;
  nxGetCurrentXbeNtPath(targetPath);

  finalSeparator = strrchr(targetPath, '\\');
  *(finalSeparator + 1) = '\0';
  nxMountDrive(Letter, targetPath);
}
#endif

int init_systems()
{
  bool use_dhcp = true;

  if (!nxMountDrive('C', "\\Device\\Harddisk0\\Partition2"))
  {
    outputLine("Mounting error: Could not mount drive C\n");
  }
  if (!nxMountDrive('E', "\\Device\\Harddisk0\\Partition1"))
  {
    outputLine("Mounting error: Could not mount drive E\n");
  }
  if (!nxMountDrive('F', "\\Device\\Harddisk0\\Partition6"))
  {
    outputLine("Mounting warning: Could not mount drive F\n");
  }
  if (!nxMountDrive('G', "\\Device\\Harddisk0\\Partition7"))
  {
    outputLine("Mounting warning: Could not mount drive G\n");
  }
  if (!nxMountDrive('X', "\\Device\\Harddisk0\\Partition3"))
  {
    outputLine("Mounting error: Could not mount drive X\n");
  }
  if (!nxMountDrive('Y', "\\Device\\Harddisk0\\Partition4"))
  {
    outputLine("Mounting error: Could not mount drive Y\n");
  }
  if (!nxMountDrive('Z', "\\Device\\Harddisk0\\Partition5"))
  {
    outputLine("Mounting error: Could not mount drive Z\n");
  }
  // if (nxIsDriveMounted('D'))
  // {
  //   nxUnmountDrive('D');
  // }
  // if (!nxMountDrive('D', "\\Device\\CdRom0"))
  // {
  //   outputLine("Mounting warning: Could not mount DVD drive\n");
  // }
  if (setupNetwork(&use_dhcp) != 0)
  {
    outputLine("Network setup failed.");
    return 1;
  }
  return 0;
}
