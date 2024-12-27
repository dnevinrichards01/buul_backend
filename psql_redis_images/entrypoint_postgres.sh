bash /usr/local/bin/docker-entrypoint.sh postgres
cp /conf_files/pg_hba.conf /var/lib/postgresql/data/pg_hba.conf
cp /conf_files/postgresql.conf /var/lib/postgresql/data/postgresql.conf
exec pg_ctl reload -D /var/lib/postgresql/data