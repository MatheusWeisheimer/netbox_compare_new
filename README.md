# netbox-compare

Plugin do NetBox 4.5 que compara o que o NetBox documenta sobre um equipamento com o que ele executa.

## Instalação

git clone https://github.com/MatheusWeisheimer/netbox_compare_new.git

sudo /opt/netbox/venv/bin/pip install ./packages/access ./packages/plugin

## Configuração

1. Em `/opt/netbox/netbox/netbox/configuration.py`:

PLUGINS = ["netbox_compare"]
PLUGINS_CONFIG = {
    "netbox_compare": {"credentials_file": "/etc/netbox/compare/devices.toml"},
}

2. Crie o arquivo de credenciais (modelo em `.secrets/devices.example.toml`), com uma tabela por
   equipamento, usando o nome dele no NetBox:

[devices."rtr-poa-01"]
username = "..."
password = "..."

   `chmod 600`, dono = usuário do `netbox-rq`.

3. Migre e reinicie:

cd /opt/netbox/netbox
sudo /opt/netbox/venv/bin/python manage.py migrate
sudo systemctl restart netbox netbox-rq
```
