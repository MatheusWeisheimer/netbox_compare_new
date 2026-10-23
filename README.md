# netbox-compare

Plugin do NetBox 4.5 que compara o que o NetBox documenta sobre um equipamento com o que ele executa.

## Instalação

### 1. Instalar o plugin

```bash
git clone https://github.com/MatheusWeisheimer/netbox_compare_new.git
cd netbox_compare_new
sudo /opt/netbox/venv/bin/pip install ./packages/access ./packages/plugin
```

### 2. Habilitar o plugin

Edite `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = ["netbox_compare"]

PLUGINS_CONFIG = {
    "netbox_compare": {
        "credentials_file": "/etc/netbox/compare/devices.toml",
    },
}
```

### 3. Criar o arquivo de credenciais

Copie o modelo e edite:

```bash
sudo mkdir -p /etc/netbox/compare
sudo cp .secrets/devices.example.toml /etc/netbox/compare/devices.toml
sudo nano /etc/netbox/compare/devices.toml
```

Use uma tabela por equipamento, com o mesmo nome do dispositivo no NetBox:

```toml
[devices."rtr-poa-01"]
username = "..."
password = "..."
```

### 4. Aplicar migrações

```bash
cd /opt/netbox
sudo /opt/netbox/venv/bin/python netbox/manage.py migrate
```
