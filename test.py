import datetime
from server.notion_client import NOTION
from server.config import SETTINGS

now = datetime.datetime.now(datetime.timezone.utc)
props = {
    'CLIENTE_ID': 'test_id',
    'NOMBRE_CLIENTE': 'test_name',
    'VOUCHER_URL': 'https://aura.local/test',
    'FECHA_DETECTADA': now.date().isoformat(),
    'HORA_DETECTADA': now.strftime('%H:%M'),
    'METODO_PAGO': 'Yape',
    'MONTO_TRANSFERIDO': 49.9,
    'VALIDACION_IA': 'APROBADO',
    'OBSERVACION': 'Prueba',
    'NOMBRE_ESPERADO': 'AURA Boutique',
    'NUMERO_OPERACION': 'TEST-123'
}

original_update = NOTION._client.pages.update
def test_update(*args, **kwargs):
    print("PROPS TO UPDATE:", kwargs.get('properties'))
    return original_update(*args, **kwargs)

NOTION._client.pages.update = test_update

try:
    NOTION.registrar_voucher('ORD-0002', 'https://aura.local/test', 49.9, 'Yape', 'test-user', props)
except Exception as e:
    import traceback
    traceback.print_exc()
