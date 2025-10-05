from fcontrol_api.utils.router_loader import load_routers

# Carrega todos os roteadores deste pacote e subpacotes
router = load_routers(__path__, __name__)
