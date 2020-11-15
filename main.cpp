#include "config.hpp"
#include "outputLine.h"
#include "subsystems.h"

#include "ftpServer.h"

int main(void)
{
  ftpConfig ftp_config;

  int init = init_systems();

  if (init <= 1)
  {
    bool running = true;
    if (init == 0)
    {
      ftpServer s(&ftp_config);
      s.init();
      s.run();
    }
  }
  else
  {
    outputLine("Something went wrong :( Error code: %i", init);
  }
}
