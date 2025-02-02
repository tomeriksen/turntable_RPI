Kontrollera att vi kör på Linux
ifeq ($(shell uname),Linux)
else
	$(error Denna Makefile stöder endast Linux.)
endif

# Variabler – ändra vid behov
PREFIX         ?= /usr/local
BINDIR         ?= $(PREFIX)/bin
TEMPLATEDIR    ?= $(BINDIR)/templates
SYSTEMDSERVICE ?= /etc/systemd/system/homepod-web.service
PYTHON         ?= python3

# Filnamn
SCRIPT_SRC     := homepod-web.py
SCRIPT_DST     := $(BINDIR)/homepod-web.py
TEMPLATE_SRC   := templates/index.html
TEMPLATE_DST   := $(TEMPLATEDIR)/index.html
SERVICE_SRC    := homepod-web.service

.PHONY: all install install-deps install-script install-template install-service \
        start stop restart status logs run uninstall clean help

all: install
	@echo "Installation klar – starta tjänsten med: make start"

help:
	@echo "Tillgängliga mål:"
	@echo "  make install       – Installerar beroenden, skript, mall och systemd-tjänst"
	@echo "  make uninstall     – Tar bort installerade filer och stänger tjänsten"
	@echo "  make start         – Startar och aktiverar tjänsten"
	@echo "  make stop          – Stoppar tjänsten"
	@echo "  make restart       – Startar om tjänsten"
	@echo "  make status        – Visar tjänstens status"
	@echo "  make logs          – Visar tjänstens loggar"
	@echo "  make run           – Kör webbservern direkt (för test)"

install: install-deps install-script install-template install-service
	@echo "Installation klar – starta tjänsten med: make start"

# Installera Flask via pip
install-deps:
	$(PYTHON) -m pip install flask

# Kopiera Python-skriptet till rätt plats och gör det exekverbart
install-script:
	install -Dm755 $(SCRIPT_SRC) $(SCRIPT_DST)

# Kopiera HTML-mallen till rätt plats
install-template:
	install -Dm644 $(TEMPLATE_SRC) $(TEMPLATE_DST)

# Installera systemd-tjänsten
install-service:
	@echo "Installerar systemd-tjänst i $(SYSTEMDSERVICE)"
	# Ersätt "User=tomeriksen" med aktuell användare (använder variabeln USER)
	sed "s/User=tomeriksen/User=$(USER)/" $(SERVICE_SRC) | install -Dm644 /dev/stdin $(SYSTEMDSERVICE)
	sudo systemctl daemon-reload

# Starta och aktivera tjänsten
start:
	sudo systemctl start homepod-web
	sudo systemctl enable homepod-web
	@echo "Tjänsten startad."

# Stoppa tjänsten
stop:
	sudo systemctl stop homepod-web
	@echo "Tjänsten stoppad."

# Starta om tjänsten
restart:
	sudo systemctl restart homepod-web
	@echo "Tjänsten omstartad."

# Visa status för tjänsten
status:
	sudo systemctl status homepod-web

# Visa loggar för tjänsten
logs:
	sudo journalctl -u homepod-web -f

# Kör webbservern direkt (utan systemd) – bra för test
run:
	$(PYTHON) $(SCRIPT_DST)

# Avinstallera – tar bort installerade filer och stoppar tjänsten
uninstall: stop
	sudo systemctl disable homepod-web
	sudo rm -f $(SCRIPT_DST)
	sudo rm -rf $(TEMPLATEDIR)
	sudo rm -f $(SYSTEMDSERVICE)
	sudo systemctl daemon-reload
	@echo "Avinstallation klar."

# Rensa eventuella temporära filer (vid behov)
clean:
	@echo "Inget att rensa."
