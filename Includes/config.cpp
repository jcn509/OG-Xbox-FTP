#include "config.hpp"

ftpConfig::ftpConfig()
{
  enable = true;
  username = "xbox";
  password = "xbox";
  port = 21;
}

void ftpConfig::setEnabled(bool val)
{
  if (enable != val)
  {
    enable = val;
  }
}

void ftpConfig::setUser(std::string const &user)
{
  if (username.compare(user))
  {
    username = user;
  }
}

void ftpConfig::setPassword(std::string const &pwd)
{
  if (password.compare(pwd))
  {
    password = pwd;
  }
}

void ftpConfig::setPort(int p)
{
  if (port != p)
  {
    port = p;
  }
}