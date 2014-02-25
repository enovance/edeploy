WWW_DIR=$(DESTDIR)/usr/lib/cgi-bin
WWW_CONF_DIR=/var/lib/edeploy
WWW_LOG_DIR=$(WWW_CONF_DIR)/logs
WWW_HW_DIR=$(WWW_CONF_DIR)/hw
WWW_HL_DIR=$(WWW_CONF_DIR)/health
WWW_CONFIG_DIR=$(DESTDIR)$(WWW_CONF_DIR)
WWW_LOGGING_DIR=$(DESTDIR)$(WWW_LOG_DIR)
WWW_HARDWARE_DIR=$(DESTDIR)$(WWW_HW_DIR)
WWW_HEALTH_DIR=$(DESTDIR)$(WWW_HL_DIR)
WWW_USER=www-data
ETC_DIR=$(DESTDIR)/etc
SHARE_BUILD_DIR=$(DESTDIR)/usr/share/edeploy/$(BUILD_DIR)
ANSIBLE_DIR=$(DESTDIR)/usr/share/ansible
PYSRC=$(shell ls src/*.py server/*.py ansible/library/edeploy ansible/library/cp | grep -v test_)

install-www:
	mkdir -p $(WWW_DIR) && 	chmod 755 $(WWW_DIR)
	mkdir -p $(WWW_CONFIG_DIR) && chmod 755 $(WWW_CONFIG_DIR)
	mkdir -p $(WWW_LOGGING_DIR) && chmod 755 $(WWW_LOGGING_DIR)
	mkdir -p $(WWW_HARDWARE_DIR) && chmod 755 $(WWW_HARDWARE_DIR)
	mkdir -p $(WWW_HEALTH_DIR) && chmod 755 $(WWW_HEALTH_DIR)
	mkdir -p $(ETC_DIR) && chmod 755 $(ETC_DIR)
	mkdir -p $(ANSIBLE_DIR) && chmod 755 $(ANSIBLE_DIR)
	if [ -f $(ETC_DIR)/edeploy.conf ]; then cp -f $(ETC_DIR)/edeploy.conf $(ETC_DIR)/edeploy.conf.backup; fi
	install -m 644 server/edeploy.conf $(ETC_DIR)/
	install -m 755 server/upload.py server/matcher.py $(WWW_DIR)/
	install -m 644 config/*.specs $(WWW_CONFIG_DIR)/
	install -m 644 config/*.configure $(WWW_CONFIG_DIR)/
	install -m 755 ansible/library/edeploy $(ANSIBLE_DIR)/
	install -m 755 ansible/library/cp $(ANSIBLE_DIR)/
	cd config; for file in *.cmdb state; do echo $$file; if [ ! -e $(WWW_CONFIG_DIR)/$$file ]; then install -m 644 $$file $(WWW_CONFIG_DIR)/ ; fi ; done
	chown $(WWW_USER):$(WWW_USER) $(WWW_CONFIG_DIR)/*.cmdb $(WWW_CONFIG_DIR)/state
	chown $(WWW_USER):$(WWW_USER) $(WWW_LOGGING_DIR) $(WWW_HARDWARE_DIR) $(WWW_HEALTH_DIR)
	sed -i -e "s|^CONFIGDIR=.*|CONFIGDIR=$(WWW_CONFIG_DIR)|" $(ETC_DIR)/edeploy.conf
	sed -i -e "s|^LOGDIR=.*|LOGDIR=$(WWW_LOGGING_DIR)|" $(ETC_DIR)/edeploy.conf
	sed -i -e "s|^HWDIR=.*|HWDIR=$(WWW_HARDWARE_DIR)|" $(ETC_DIR)/edeploy.conf
	sed -i -e "s|^HEALTHDIR=.*|HEALTHDIR=$(WWW_HEALTH_DIR)|" $(ETC_DIR)/edeploy.conf

install-build:
	mkdir -p $(SHARE_BUILD_DIR) && chmod 755 $(SHARE_BUILD_DIR)
	cp -a build/* $(SHARE_BUILD_DIR)/

test:
	nosetests src server

quality: pylint flake8

flake8:
	flake8 $(PYSRC)

pylint:
	-pylint -f parseable $(PYSRC)
