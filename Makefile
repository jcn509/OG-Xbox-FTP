XBE_TITLE = OGXboxFTP
INCDIR = $(CURDIR)/Includes

SRCS += $(INCDIR)/config.cpp \
	$(INCDIR)/ftpConnection.cpp \
	$(INCDIR)/ftpServer.cpp \
	$(CURDIR)/main.cpp \
	$(INCDIR)/networking.cpp \
	$(INCDIR)/outputLine.cpp \
	$(INCDIR)/subsystems.cpp
	

NXDK_DIR ?= $(CURDIR)/../nxdk
NXDK_SDL = n
NXDK_CXX = y
NXDK_NET = y
NXDK_DISABLE_AUTOMOUNT_D = y

GEN_XISO = ${XBE_TITLE}.iso

CXXFLAGS += -I$(CURDIR) -I$(INCDIR) -Wall -Wextra -std=gnu++11
CFLAGS   += -std=gnu11


include $(NXDK_DIR)/Makefile
