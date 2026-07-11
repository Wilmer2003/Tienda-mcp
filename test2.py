import traceback
from server.store_logic import TIENDA
from server.models import ItemCarrito

TIENDA._carritos['test_user'] = []
TIENDA._carritos['test_user'].append(ItemCarrito(producto_id='P001', nombre='Polo', cantidad=1, precio_unitario=50.0, subtotal=50.0))
TIENDA._carritos['test_user'].append(ItemCarrito(producto_id='P002', nombre='Pantalon', cantidad=1, precio_unitario=60.0, subtotal=60.0))

res = TIENDA.crear_pedido('test_user')
p_id = res.datos['pedido_id']

print('P_ID:', p_id)
p_ids = p_id.split(',')
pedidos = [TIENDA._pedidos.get(pid) for pid in p_ids]
print('pedidos contains None?', None in pedidos)

try:
    p = TIENDA.consultar_pedido(p_id)
    print('P:', p)
except Exception as e:
    print('EXCEPTION:')
    traceback.print_exc()
