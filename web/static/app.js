const productImages = {
  'P001': 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&q=80',
  'P002': 'https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=400&q=80',
  'P013': 'https://images.unsplash.com/photo-1556821840-3a63f95609a7?w=400&q=80',
  'P014': 'https://images.unsplash.com/photo-1529374255404-311a2a4f1fd9?w=400&q=80',
  'P015': 'https://images.unsplash.com/photo-1618517351616-38fb9c5210c6?w=400&q=80',
  'P031': 'https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=400&q=80',
  'P003': 'https://images.unsplash.com/photo-1542272604-787c3835535d?w=400&q=80',
  'P004': 'https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=400&q=80',
  'P016': 'https://images.unsplash.com/photo-1582552938357-32b906df40cb?w=400&q=80',
  'P017': 'https://images.unsplash.com/photo-1555689502-c4b22d76c56f?w=400&q=80',
  'P018': 'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=400&q=80',
  'P032': 'https://images.unsplash.com/photo-1552902865-b72c031ac5ea?w=400&q=80',
  'P005': 'https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=400&q=80',
  'P006': 'https://images.unsplash.com/photo-1539008835657-9e8e9680c956?w=400&q=80',
  'P019': 'https://images.unsplash.com/photo-1495385794356-15371f348c31?w=400&q=80',
  'P020': 'https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=400&q=80',
  'P021': 'https://images.unsplash.com/photo-1605763240000-7e93b172d754?w=400&q=80',
  'P033': 'https://images.unsplash.com/photo-1515347619362-e64e9a5be433?w=400&q=80',
  'P007': 'https://images.unsplash.com/photo-1549298916-b41d501d3772?w=400&q=80',
  'P008': 'https://images.unsplash.com/photo-1614252339460-e1b9b5f93976?w=400&q=80',
  'P022': 'https://images.unsplash.com/photo-1638247025967-b4e38f787b76?w=400&q=80',
  'P023': 'https://images.unsplash.com/photo-1608231387042-66d1773070a5?w=400&q=80',
  'P024': 'https://images.unsplash.com/photo-1562183241-b937e95585b6?w=400&q=80',
  'P034': 'https://images.unsplash.com/photo-1611244419377-b0a760c19719?w=400&q=80',
  'P009': 'https://images.unsplash.com/photo-1551028719-00167b16eac5?w=400&q=80',
  'P010': 'https://images.unsplash.com/photo-1539533113208-f6df8cc8b543?w=400&q=80',
  'P025': 'https://images.unsplash.com/photo-1576871337622-98d48d1cf531?w=400&q=80',
  'P026': 'https://images.unsplash.com/photo-1545594861-3bef436fb5b1?w=400&q=80',
  'P027': 'https://images.unsplash.com/photo-1592878904946-b3ce8ae24ea5?w=400&q=80',
  'P035': 'https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=400&q=80',
  'P011': 'https://images.unsplash.com/photo-1624222247344-550fb60583dc?w=400&q=80',
  'P012': 'https://images.unsplash.com/photo-1604928135894-1a9be2dc541b?w=400&q=80',
  'P028': 'https://images.unsplash.com/photo-1511499767150-a48a237f0083?w=400&q=80',
  'P029': 'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400&q=80',
  'P030': 'https://images.unsplash.com/photo-1524592094714-0f0654e20314?w=400&q=80',
  'P036': 'https://images.unsplash.com/photo-1588850561407-ed78c282e89b?w=400&q=80',
};
/**
 * Nexus Electronics — app.js
 * Lógica del lado del cliente para interactuar con la API del sistema multi-agente.
 */

// Estado global de la aplicación
let currentUser = 'cliente-01';
let currentProfile = null;
let allProducts = [];
let activeCategory = '';
let searchQuery = '';

// Elementos del DOM
const productsGrid = document.getElementById('products-grid');
const searchInput = document.getElementById('search');
const togglePanelBtn = document.getElementById('toggle-panel');
const usuarioIdSpan = document.getElementById('usuario-id');
const openCartBtn = document.getElementById('open-cart');
const closeCartBtn = document.getElementById('close-cart');
const cartCountSpan = document.getElementById('cart-count');
const cartDrawer = document.getElementById('cart-drawer');
const cartItemsContainer = document.getElementById('cart-items');
const cartTotalSpan = document.getElementById('cart-total');
const checkoutBtn = document.getElementById('checkout-btn');
const checkoutModal = document.getElementById('checkout-modal');
const closeCheckoutBtn = document.getElementById('close-checkout');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatLog = document.getElementById('chat-log');
const toolsLogContainer = document.getElementById('tools-log');
const eventsLog = document.getElementById('events-log');
const delegasLog = document.getElementById('delegas-log');

function applyAuthenticatedUser(profile, refreshCart = true) {
  if (!profile || !profile.uid) return;
  const previousUser = currentUser;
  currentProfile = profile;
  currentUser = profile.uid;
  usuarioIdSpan.textContent = currentUser;
  if (refreshCart && previousUser !== currentUser && document.readyState !== 'loading') {
    fetchCart();
  }
}

window.AURA_setAuthenticatedUser = (profile) => applyAuthenticatedUser(profile);

async function authFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  let token = null;
  if (typeof window.AURA_getIdToken === 'function') {
    try {
      token = await window.AURA_getIdToken();
    } catch (_) {
      token = null;
    }
  }
  token = token || localStorage.getItem('aura_id_token');
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(url, { ...options, headers });
}

function currentCustomer() {
  const displayName = (currentProfile?.display_name || currentProfile?.email || currentUser).trim();
  const parts = displayName.split(/\s+/).filter(Boolean);
  return {
    email: currentProfile?.email || `${currentUser}@tienda-mcp.local`,
    nombres: parts[0] || currentUser,
    apellidos: parts.slice(1).join(' ') || 'Cliente',
    displayName,
    telefono: '999999999'
  };
}

// Inicialización
document.addEventListener('DOMContentLoaded', () => {
  init();
});

function init() {
  // Configurar usuario actual
  try {
    const cachedProfile = JSON.parse(localStorage.getItem('aura_user') || 'null');
    if (cachedProfile) applyAuthenticatedUser(cachedProfile, false);
  } catch (_) {}
  currentUser = currentProfile?.uid || usuarioIdSpan.textContent.trim() || 'cliente-01';

  // Configurar pestañas del asistente
  setupTabs();

  // Configurar botones de filtrado por categoría
  setupCategoryFilters();

  // Escuchar entrada de búsqueda
  searchInput.addEventListener('input', (e) => {
    searchQuery = e.target.value;
    renderProducts();
  });

  // Mostrar / ocultar panel del asistente
  togglePanelBtn.addEventListener('click', () => {
    document.body.classList.toggle('panel-hidden');
  });

  // Abrir y cerrar carrito
  openCartBtn.addEventListener('click', () => {
    cartDrawer.classList.add('open');
    fetchCart();
  });
  

  // Checkout modal
  checkoutBtn.addEventListener('click', () => {
    // Verificar si el carrito está vacío antes de abrir checkout
    const count = parseInt(cartCountSpan.textContent) || 0;
    if (count === 0) {
      showToast('Tu carrito está vacío.', 'err');
      return;
    }
    cartDrawer.classList.remove('open');
    checkoutModal.classList.add('open');
  });

  closeCheckoutBtn.addEventListener('click', () => {
    checkoutModal.classList.remove('open');
  });

  // Configurar botones de pago en el modal
  setupPaymentMethods();

  // Formulario de chat
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const msg = chatInput.value.trim();
    if (!msg) return;
    chatInput.value = '';
    sendMessage(msg);
  });

  // Acciones rápidas (quick actions)
  document.querySelectorAll('.quick').forEach(btn => {
    btn.addEventListener('click', () => {
      const msg = btn.getAttribute('data-msg');
      if (msg) {
        sendMessage(msg);
      }
    });
  });

  // Cargar catálogo inicial y carrito
  fetchProducts();
  fetchCart();

  // Polling de eventos (cada 1.5 segundos)
  pollEvents();
  setInterval(pollEvents, 1500);
}

// Configuración de Pestañas (Chat / Agentes / Eventos)
function setupTabs() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      // Quitar active de todas las pestañas y paneles
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      // Añadir active a la pestaña clickeada
      tab.classList.add('active');
      const targetPaneId = `tab-${tab.getAttribute('data-tab')}`;
      const targetPane = document.getElementById(targetPaneId);
      if (targetPane) {
        targetPane.classList.add('active');
      }
    });
  });
}

// Configuración de filtros por categoría
function setupCategoryFilters() {
  document.querySelectorAll('.filter').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeCategory = btn.getAttribute('data-cat') || '';
      renderProducts();
    });
  });
}

// Configuración de métodos de pago en el modal
function setupPaymentMethods() {
  document.querySelectorAll('.pay-methods button').forEach(btn => {
    btn.addEventListener('click', () => {
      const method = btn.getAttribute('data-method');
      if (method) {
        checkoutModal.classList.remove('open');
        
        // Switch to chat view so the user can see the agent processing the payment
        document.querySelectorAll('.menu-item[data-view]').forEach(b => b.classList.remove('active'));
        const chatBtn = document.querySelector('.menu-item[data-view="chat"]');
        if(chatBtn) chatBtn.classList.add('active');
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        const chatView = document.getElementById('view-chat');
        if(chatView) chatView.classList.add('active');
        
        sendMessage(`Quiero crear pedido y pagar con ${method}`);
      }
    });
  });
}

// Cargar productos desde el backend
async function fetchProducts() {
  try {
    const res = await fetch('/api/productos');
    if (!res.ok) throw new Error('Error al cargar catálogo');
    allProducts = await res.json();
    renderProducts();
  } catch (err) {
    console.error(err);
    productsGrid.innerHTML = `<div class="loading" style="color: var(--err);">Error al cargar el catálogo de productos.</div>`;
  }
}

// Filtrar y renderizar los productos en la cuadrícula
function renderProducts() {
  if (!allProducts.length) {
    productsGrid.innerHTML = `<div class="loading">Cargando catálogo...</div>`;
    return;
  }

  // Filtrar
  const filtered = allProducts.filter(p => {
    // Filtro por categoría
    if (activeCategory && p.categoria.toLowerCase() !== activeCategory.toLowerCase()) {
      return false;
    }
    // Filtro por búsqueda
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchName = p.nombre.toLowerCase().includes(q);
      const matchBrand = p.marca.toLowerCase().includes(q);
      const matchDesc = p.descripcion.toLowerCase().includes(q);
      const matchId = p.id.toLowerCase().includes(q);
      if (!matchName && !matchBrand && !matchDesc && !matchId) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    productsGrid.innerHTML = `<div class="loading">No se encontraron productos coincidentes.</div>`;
    return;
  }

  // Renderizar
  productsGrid.innerHTML = filtered.map(p => {
    const isAgotado = p.stock === 0;
    const isBajo = p.stock > 0 && p.stock <= 2;
    let stockClass = '';
    let stockText = `Stock: ${p.stock}`;

    if (isAgotado) {
      stockClass = 'agotado';
      stockText = 'Agotado';
    } else if (isBajo) {
      stockClass = 'bajo';
      stockText = `¡Últimas ${p.stock} unids!`;
    }

    // Inicial estética para el thumb (primera letra del nombre, no el ID)
    const inicial = (p.nombre || '?').trim().charAt(0).toUpperCase();
    return `
      <div class="card" data-id="${p.id}">
        <div class="thumb" style="background-image: url('${productImages[p.id] || ''}');"></div>
        <div class="body">
          <div class="brand-line">${p.marca}</div>
          <div class="name">${p.nombre}</div>
          <p class="descr">${p.descripcion.substring(0,60)}...</p>
          <div class="meta">
            <div class="price">S/ ${p.precio.toFixed(2)}</div>
          </div>
          <button class="add" ${isAgotado ? 'disabled' : ''} data-id="${p.id}">
            ${isAgotado ? 'Agotado' : 'Añadir al carrito 🛒'}
          </button>
        </div>
      </div>
    `;
  }).join('');

  // Agregar eventos a los botones de añadir al carrito
  productsGrid.querySelectorAll('.add').forEach(btn => {
    btn.addEventListener('click', () => {
      const pid = btn.getAttribute('data-id');
      sendMessage(`Agrega ${pid} al carrito`);
    });
  });
}

// Cargar estado del carrito
async function fetchCart() {
  try {
    const res = await authFetch(`/api/carrito/${currentUser}`);
    if (!res.ok) throw new Error('Error al obtener carrito');
    const cart = await res.json();
    renderCart(cart);
  } catch (err) {
    console.error(err);
  }
}

// Renderizar contenido del carrito
function renderCart(cart) {
  // Actualizar contador en la cabecera
  cartCountSpan.textContent = cart.cantidad_items || 0;

  // Actualizar total
  cartTotalSpan.textContent = `S/ ${(cart.total || 0).toFixed(2)}`;

  // Actualizar items
  const items = cart.items || [];
  if (items.length === 0) {
    cartItemsContainer.innerHTML = `<div style="text-align: center; color: var(--text-dim); padding: 40px 0;">Tu carrito está vacío.</div>`;
    return;
  }

  cartItemsContainer.innerHTML = items.map(item => `
    <div class="cart-item">
      <img src="${productImages[item.producto_id] || ''}" alt="${item.nombre}">
      <div class="cart-item-details">
        <h4>${item.nombre}</h4>
        <div class="price">S/ ${item.precio_unitario.toFixed(2)}</div>
        <div class="cart-item-actions">
           <div class="qty-control">
             <button onclick="modificarCarritoUI('${item.producto_id}', 'eliminar', 1)">-</button>
             <span>${item.cantidad}</span>
             <button onclick="modificarCarritoUI('${item.producto_id}', 'agregar', 1)">+</button>
           </div>
           <button class="trash-btn" onclick="modificarCarritoUI('${item.producto_id}', 'eliminar', ${item.cantidad})">
             <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
           </button>
        </div>
      </div>
    </div>
  `).join('');
}

// Enviar un mensaje de chat al orquestador multi-agente
async function sendMessage(messageText) {
  if (!messageText) return;

  // 1) Añadir el mensaje del usuario al chat log
  appendChatMessage('user', 'Usuario', messageText);

  // 2) Mostrar indicador de "escribiendo..." o estado de carga
  const typingIndicator = appendChatMessage('agent typing', 'Asistente', 'Razonando...');

  try {
    // 3) POST a la API
    const res = await authFetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario_id: currentUser, mensaje: messageText })
    });

    if (!res.ok) throw new Error('Error en el servicio de chat');
    const resp = await res.json();

    // 4) Quitar indicador de cargando
    typingIndicator.remove();

        const tools = resp.tools_invocadas || [];
    const agenteName = resp.agente || 'asistente';
    const msgTexto = resp.mensaje || '';

    // 5) Renderizar respuesta final del agente
    const formattedMeta = `
      <strong>${agenteName.toUpperCase()}</strong> 
      <span style="color: var(--text-dim); font-size: 10px; margin-left: 6px;">${resp.latencia_ms || 0}ms</span>
      ${tools.length > 0 ? `<span style="background: var(--border); color: var(--accent); padding: 1px 5px; border-radius: 4px; font-size: 10px; margin-left: 6px;" title="${tools.join(', ')}">🛠️ ${tools.length} tools</span>` : ''}
    `;
    appendChatMessage(`agent ${agenteName}`, formattedMeta, msgTexto, true);

    // 5.b) Si Finanzas devolvio datos de pago, renderizar tarjeta especial
    if (resp.datos && resp.datos.pago_info) {
      renderPagoCard(resp.datos.pago_info);
    }

    // 6) Resaltar el agente activo en la pestaña "Agentes"
    updateAgentHighlight(agenteName);

    // 7) Registrar tools en el historial de tools
    if (tools.length > 0) {
      appendToolsLog(agenteName, tools);
    }

    // 8) Mostrar toast rápido de estado
    if (resp.exito) {
      if (messageText.toLowerCase().includes('agrega')) {
        showToast('Prenda añadida a tu carrito', 'ok');
      } else if (messageText.toLowerCase().includes('pagar') || messageText.toLowerCase().includes('yape') || messageText.toLowerCase().includes('tarjeta')) {
        if (resp.mensaje.toLowerCase().includes('aprobad') || resp.mensaje.toLowerCase().includes('confirmado')) {
          showToast('¡Compra confirmada!', 'ok');
        }
      }
    } else {
      showToast(resp.mensaje, 'err');
    }

    // 9) Refrescar catálogo y carrito para sincronizar inventario
    fetchProducts();
    fetchCart();

  } catch (err) {
    console.error(err);
    typingIndicator.remove();
    appendChatMessage('agent err', 'Error', 'No se pudo conectar con el asistente. Asegúrate de que el servidor está corriendo.');
    showToast('Error de comunicación con el servidor', 'err');
  }
}

// Función auxiliar para añadir mensajes al log
function appendChatMessage(senderClass, senderHeader, text, isHtml = false) {
  const msgDiv = document.createElement('div');
  msgDiv.className = `msg ${senderClass}`;
  const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
  let headHtml = senderClass.includes('user') ? 
    `<div style="font-size:10px; opacity:0.7; text-align:right; margin-bottom:4px;">${time} <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" style="vertical-align:middle"><polyline points="20 6 9 17 4 12"></polyline></svg></div>` :
    `<div class="msg-head"><span class="agent-icon">✨</span> ${senderHeader}</div>`;
  
  msgDiv.innerHTML = `
    ${headHtml}
    <div class="msg-body"></div>
    ${senderClass.includes('agent') ? `<div style="font-size:10px; color:var(--text-dim); margin-top:8px;">${time}</div>` : ''}
  `;
  
  const bodyDiv = msgDiv.querySelector('.msg-body');
  if (isHtml) {
    bodyDiv.innerHTML = text;
  } else {
    bodyDiv.textContent = text;
  }

  chatLog.appendChild(msgDiv);
  chatLog.scrollTop = chatLog.scrollHeight;
  return msgDiv;
}

// Resaltar el agente en la pestaña de Agentes
function updateAgentHighlight(activeAgent) {
  document.querySelectorAll('.agent-card').forEach(card => {
    card.classList.remove('active');
    if (card.getAttribute('data-agent') === activeAgent) {
      card.classList.add('active');
    }
  });
}

// Añadir registros de tools invocadas al panel
function appendToolsLog(agent, tools) {
  // Limpiar el aviso inicial si existe
  if (toolsLogContainer.querySelector('em')) {
    toolsLogContainer.innerHTML = '';
  }

  tools.forEach(tool => {
    const line = document.createElement('div');
    line.className = 'tool-line';
    const timeStr = new Date().toLocaleTimeString();
    line.innerHTML = `[${timeStr}] Agente <strong style="color: var(--primary);">${agent}</strong> llamó a: <strong>${tool}</strong>`;
    toolsLogContainer.appendChild(line);
  });
  toolsLogContainer.scrollTop = toolsLogContainer.scrollHeight;
}

// Consultar los eventos del bus del backend
async function pollEvents() {
  try {
    const res = await fetch('/api/eventos');
    if (!res.ok) return;
    const events = await res.json();
    renderEvents(events);
  } catch (err) {
    console.error('Error polling events:', err);
  }
}

// Renderizar eventos en el tab correspondiente
function renderEvents(events) {
  if (!eventsLog) return;
  if (!events || events.length === 0) {
    eventsLog.innerHTML = '<em style="color: var(--text-dim);">No hay eventos publicados aún</em>';
    return;
  }

  // Mapeamos los eventos y los mostramos ordenados de más nuevo a más antiguo
  eventsLog.innerHTML = events.map(ev => {
    // tipo de evento ej: "stock.agotado" -> clase "stock-agotado"
    const typeClass = ev.tipo.replace(/\./g, '-');
    const timeStr = new Date(ev.timestamp).toLocaleTimeString();

    // Simplificar datos para que sea legible
    let datosHtml = '';
    if (ev.datos && Object.keys(ev.datos).length > 0) {
      datosHtml = `<div class="ev-data">${JSON.stringify(ev.datos)}</div>`;
    }

    return `
      <div class="event-item ${typeClass}">
        <div class="ev-tipo">${ev.tipo}</div>
        <div class="ev-from">Publicado por: ${ev.publicado_por} | ${timeStr}</div>
        ${datosHtml}
      </div>
    `;
  }).reverse().join('');

  // Renderizar tambien delegaciones (jefe -> X) en su propia pestana
  renderDelegaciones(events.filter(e => e.tipo === 'jefe.delega'));
}

// Renderiza el log de delegaciones del jefe (subset del bus, mas legible)
function renderDelegaciones(delegas) {
  if (!delegasLog) return;
  if (!delegas || delegas.length === 0) {
    delegasLog.innerHTML = '<em style="color: var(--text-dim);">Aún no hay delegaciones registradas.</em>';
    return;
  }
  delegasLog.innerHTML = delegas.slice().reverse().map(ev => {
    const time = new Date(ev.timestamp).toLocaleTimeString();
    const d = ev.datos || {};
    const target = d.delega_a || '?';
    const intent = d.intent || '?';
    const msg = d.mensaje || '';
    const via = d.via || '';
    return `
      <div class="delega-item">
        <div class="delega-flow">JEFE<span class="arrow">→</span>${target.toUpperCase()}</div>
        <div class="delega-msg">"${msg}"</div>
        <div class="delega-meta">intent: ${intent} · via: ${via} · ${time}</div>
      </div>
    `;
  }).join('');
}

let niubizScriptLoaded = '';

function loadNiubizScript(src) {
  if (window.VisanetCheckout && niubizScriptLoaded === src) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-niubiz-checkout="${src}"]`);
    if (existing) {
      existing.addEventListener('load', resolve, { once: true });
      existing.addEventListener('error', reject, { once: true });
      return;
    }
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.dataset.niubizCheckout = src;
    script.onload = () => {
      niubizScriptLoaded = src;
      resolve();
    };
    script.onerror = () => reject(new Error('No se pudo cargar checkout.js de Niubiz'));
    document.head.appendChild(script);
  });
}

async function iniciarPagoNiubiz(info, button) {
  button.disabled = true;
  button.textContent = 'Abriendo Niubiz...';
  const customer = currentCustomer();
  try {
    const res = await authFetch('/api/niubiz/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pedido_id: info.pedido_id,
        usuario_id: currentUser,
        email: customer.email,
        nombres: customer.nombres,
        apellidos: customer.apellidos,
        telefono: customer.telefono
      })
    });
    const session = await res.json();
    if (!res.ok || !session.exito) {
      throw new Error(session.detail || 'No se pudo iniciar Niubiz');
    }
    await loadNiubizScript(session.checkout_js_url);
    if (!window.VisanetCheckout) {
      throw new Error('Checkout Niubiz no disponible');
    }
    window.VisanetCheckout.configure({
      sessiontoken: session.session_key,
      channel: 'web',
      merchantid: session.merchant_id,
      purchasenumber: session.purchase_number,
      amount: Number(session.amount).toFixed(2),
      expirationminutes: '20',
      timeouturl: window.location.href,
      formbuttontext: 'Pagar',
      formbuttoncolor: '#b86b4b',
      cardholderemail: customer.email,
      cardholdername: customer.nombres,
      cardholderlastname: customer.apellidos,
      action: session.action_url,
      complete: function() {
        showToast('Procesando respuesta de Niubiz...', 'ok');
      },
      cancel: function() {
        button.disabled = false;
        button.textContent = info.boton_texto || 'Pagar con Niubiz';
        showToast('Pago cancelado en Niubiz', 'err');
      }
    });
    window.VisanetCheckout.open();
    button.textContent = 'Checkout abierto';
  } catch (err) {
    console.error(err);
    button.disabled = false;
    button.textContent = info.boton_texto || 'Pagar con Niubiz';
    showToast(err.message || 'Error con Niubiz', 'err');
  }
}

// Renderiza la tarjeta de pago con QR / datos bancarios y form de voucher.
function renderPagoCard(info) {
  const card = document.createElement('div');
  card.className = 'msg agent finanzas pago-card';

  let datosHtml = '';
  if (info.metodo === 'niubiz') {
    datosHtml = `
      <div class="pago-row"><span>Pasarela</span><strong>${info.pasarela}</strong></div>
      <div class="pago-row"><span>Moneda</span><strong class="mono">${info.moneda}</strong></div>
      <div class="pago-row"><span>Confirmacion</span><strong>Automatica</strong></div>
    `;
  } else if (info.metodo === 'tarjeta') {
    datosHtml = `
      <div class="pago-row"><span>Banco</span><strong>${info.banco}</strong></div>
      <div class="pago-row"><span>Cuenta</span><strong class="mono">${info.cuenta}</strong></div>
      <div class="pago-row"><span>CCI</span><strong class="mono">${info.cci}</strong></div>
      <div class="pago-row"><span>Titular</span><strong>${info.titular}</strong></div>
      <div class="pago-row"><span>RUC</span><strong class="mono">${info.ruc}</strong></div>
    `;
  } else if (info.metodo === 'yape' || info.metodo === 'plin') {
    datosHtml = `
      <div class="pago-row"><span>Número</span><strong class="mono">${info.numero}</strong></div>
      <div class="pago-row"><span>Titular</span><strong>${info.titular}</strong></div>
      <div class="pago-qr">
        <img src="${info.qr}" alt="QR ${info.metodo.toUpperCase()}" />
        <small>Escanea desde tu app ${info.metodo.toUpperCase()}</small>
      </div>
    `;
  } else if (info.metodo === 'paypal') {
    datosHtml = `
      <div class="pago-row"><span>Email PayPal</span><strong>${info.email}</strong></div>
      <div class="pago-row"><span>Titular</span><strong>${info.titular}</strong></div>
    `;
  }

  const total = (info.total || 0).toFixed(2);
  card.innerHTML = `
    <div class="msg-head">FINANZAS · DATOS DE PAGO</div>
    <div class="msg-body">
      <div class="pago-header">
        <div class="pago-metodo">${info.metodo.toUpperCase()}</div>
        <div class="pago-total">S/ ${total}</div>
      </div>
      <div class="pago-pedido">Pedido <strong>${info.pedido_id}</strong></div>
      <div class="pago-datos">${datosHtml}</div>
      ${info.requiere_pasarela ? `
        <button type="button" class="primary-btn niubiz-submit">
          ${info.boton_texto || 'Pagar con Niubiz'}
        </button>
      ` : ''}
      ${info.requiere_voucher ? `
        <form class="voucher-form" data-pedido-id="${info.pedido_id}">
          <label class="voucher-label">
            <span class="voucher-icon">📎</span>
            <span>Sube tu voucher de pago (imagen)</span>
            <input type="file" name="voucher" accept="image/*" required />
          </label>
          <div class="voucher-preview" style="display:none;">
            <img alt="preview" /><span class="voucher-filename"></span>
          </div>
          <button type="submit" class="primary-btn voucher-submit">
            Confirmar pago
          </button>
        </form>
      ` : ''}
    </div>
  `;

  // Insertar el card en el chat
  chatLog.appendChild(card);
  chatLog.scrollTop = chatLog.scrollHeight;

  const niubizButton = card.querySelector('.niubiz-submit');
  if (niubizButton) {
    niubizButton.addEventListener('click', () => iniciarPagoNiubiz(info, niubizButton));
  }

  // Conectar el form de voucher
  const form = card.querySelector('.voucher-form');
  if (form) {
    const input = form.querySelector('input[type="file"]');
    const preview = form.querySelector('.voucher-preview');
    const previewImg = preview.querySelector('img');
    const previewName = preview.querySelector('.voucher-filename');
    input.addEventListener('change', () => {
      const file = input.files[0];
      if (!file) return;
      previewName.textContent = file.name;
      const reader = new FileReader();
      reader.onload = (e) => {
        previewImg.src = e.target.result;
        preview.style.display = 'flex';
      };
      reader.readAsDataURL(file);
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const file = input.files[0];
      if (!file) { showToast('Selecciona una imagen', 'err'); return; }
      const fd = new FormData();
      fd.append('pedido_id', form.getAttribute('data-pedido-id'));
      fd.append('usuario_id', currentUser);
      fd.append('voucher', file);
      form.querySelector('button').disabled = true;
      form.querySelector('button').textContent = 'Verificando...';
      try {
        const res = await authFetch('/api/voucher', { method: 'POST', body: fd });
        const data = await res.json();
        // Mensaje del agente Finanzas verificando
        appendChatMessage('agent finanzas', 'FINANZAS · VERIFICACIÓN',
                          data.mensaje);
        if (data.exito) {
          showToast('¡Pago verificado!', 'ok');
          form.remove();
          fetchProducts(); fetchCart();
        } else {
          showToast(data.mensaje, 'err');
          form.querySelector('button').disabled = false;
          form.querySelector('button').textContent = 'Reintentar';
        }
      } catch (err) {
        showToast('Error al subir voucher', 'err');
        form.querySelector('button').disabled = false;
        form.querySelector('button').textContent = 'Confirmar pago';
      }
    });
  }
}


// Toast de notificaciones
function showToast(message, type = 'ok') {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.className = `show ${type}`;
  setTimeout(() => {
    toast.classList.remove('show');
  }, 3000);
}

async function modificarCarritoUI(productoId, accion, cantidad) {
  if (!currentUser) return;
  try {
    const res = await authFetch('/api/carrito/' + currentUser + '/modificar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ producto_id: productoId, cantidad: cantidad, accion: accion })
    });
    if (res.ok) {
      await fetchCart();
    }
  } catch (e) {
    console.error(e);
  }
}


// Wire up new header cart button
const cartHeaderBtn = document.getElementById('cart-header-btn');
if (cartHeaderBtn) {
  cartHeaderBtn.addEventListener('click', () => {
    const drawer = document.getElementById('cart-drawer');
    if (drawer) drawer.classList.add('open');
  });
}


// Cart logic updates
const cartOverlay = document.getElementById('cart-overlay');
function openCartDrawer() {
  const drawer = document.getElementById('cart-drawer');
  if(drawer) drawer.classList.add('open');
  if(cartOverlay) cartOverlay.classList.add('open');
}
function closeCartDrawer() {
  const drawer = document.getElementById('cart-drawer');
  if(drawer) drawer.classList.remove('open');
  if(cartOverlay) cartOverlay.classList.remove('open');
}

if(openCartBtn) {
  openCartBtn.removeEventListener('click', openCartBtn.onclick); // clear old
  openCartBtn.addEventListener('click', openCartDrawer);
}
if(closeCartBtn) {
  closeCartBtn.addEventListener('click', closeCartDrawer);
}
if(cartOverlay) {
  cartOverlay.addEventListener('click', closeCartDrawer);
}
const headerCartBtn = document.getElementById('cart-header-btn');
if(headerCartBtn) {
  headerCartBtn.addEventListener('click', openCartDrawer);
}

// ESC to close
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeCartDrawer();
  }
});

// Profile logic
const btnProfile = document.getElementById('btn-profile');
if(btnProfile) {
  btnProfile.addEventListener('click', () => {
    const user = window.CURRENT_FIREBASE_USER;
    if (!user) return;
    
    const pic = document.getElementById('profile-pic');
    const name = document.getElementById('profile-name');
    const email = document.getElementById('profile-email');
    const uid = document.getElementById('profile-uid');
    const provider = document.getElementById('profile-provider');
    const created = document.getElementById('profile-created');
  
    if (pic) pic.src = user.photoURL || 'https://ui-avatars.com/api/?name=' + (user.displayName || 'U') + '&background=333&color=fff';
    if (name) name.textContent = user.displayName || 'Sin nombre';
    if (email) email.textContent = user.email || 'Sin correo';
    if (uid) uid.textContent = user.uid;
    if (provider) provider.textContent = user.providerData && user.providerData.length > 0 ? user.providerData[0].providerId : 'Email/Password';
    if (created) created.textContent = user.metadata && user.metadata.creationTime ? new Date(user.metadata.creationTime).toLocaleString() : 'Desconocido';
  });
}
