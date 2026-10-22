FROM mysql:8.0

COPY fleetops.cnf /etc/mysql/conf.d/fleetops.cnf
COPY docker-entrypoint-wrapper.sh /docker-entrypoint-wrapper.sh
RUN chmod +x /docker-entrypoint-wrapper.sh

ENTRYPOINT ["/docker-entrypoint-wrapper.sh"]
CMD ["mysqld"]
