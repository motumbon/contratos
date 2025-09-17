// Helper: populate select options
function fillSelect(select, items, placeholder = 'Todas/Todos') {
  select.innerHTML = `<option value="">${placeholder}</option>`;
  for (const it of items) {
    const opt = document.createElement('option');
    opt.value = it;
    opt.textContent = it;
    select.appendChild(opt);
  }
}

function renderTable(records) {
  const tbody = document.querySelector('#data-table tbody');
  tbody.innerHTML = '';
  for (const r of records) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${r['Linea'] ?? ''}</td>
      <td>${r['Nom_Cliente'] ?? ''}</td>
      <td>${r['Nº de pedido'] ?? ''}</td>
      <td>${r['Denominación'] ?? ''}</td>
      <td>${r['Inicio de validez'] ?? ''}</td>
      <td>${r['Fin de validez'] ?? ''}</td>
    `;
    tbody.appendChild(tr);
  }
  document.getElementById('count').textContent = records.length;
}

function renderChart(buckets) {
  const labels = ['Vencidos', '0-30 días', '31-60 días', '61-90 días', '90+ días'];
  const values = labels.map(l => buckets?.[l] || 0);
  const data = [{
    x: labels,
    y: values,
    type: 'bar',
    marker: { color: ['#dc3545', '#ffc107', '#fd7e14', '#0dcaf0', '#198754'] }
  }];
  const layout = {
    margin: { t: 10, r: 10, l: 40, b: 40 },
    yaxis: { title: 'Cantidad' }
  };
  Plotly.newPlot('chart', data, layout, {displayModeBar: false, responsive: true});
}

function renderSoonest(soonest) {
  const list = document.getElementById('soonest-list');
  list.innerHTML = '';
  for (const r of soonest || []) {
    const li = document.createElement('li');
    li.className = 'list-group-item d-flex justify-content-between align-items-start';
    const content = document.createElement('div');
    content.className = 'ms-2 me-auto';
    content.innerHTML = `<div class="fw-semibold">${r['Nom_Cliente'] ?? ''} - ${r['Denominación'] ?? ''}</div>
      <div class="small text-muted">Pedido: ${r['Nº de pedido'] ?? ''} | Fin: ${r['Fin de validez'] ?? ''}</div>`;
    li.appendChild(content);
    list.appendChild(li);
  }
}

async function fetchDataWithFilters() {
  const linea = document.getElementById('filter-linea').value;
  const cliente = document.getElementById('filter-cliente').value;
  const producto = document.getElementById('filter-producto').value;
  const params = new URLSearchParams();
  if (linea) params.set('linea', linea);
  if (cliente) params.set('cliente', cliente);
  if (producto) params.set('producto', producto);
  const res = await fetch('/data' + (params.toString() ? ('?' + params.toString()) : ''));
  if (!res.ok) {
    console.error('Error cargando datos con filtros');
    return;
  }
  const data = await res.json();
  renderTable(data.records || []);
  renderChart(data.buckets || {});
  renderSoonest(data.soonest || []);
}

function setStatus(msg, type = 'muted') {
  const el = document.getElementById('status');
  el.className = `small text-${type}`;
  el.textContent = msg;
}

function showProgress(show = true) {
  const container = document.getElementById('progress-container');
  const btn = document.getElementById('upload-btn');
  container.style.display = show ? 'block' : 'none';
  btn.disabled = show;
  if (!show) {
    updateProgress(0);
  }
}

function updateProgress(percent, text = null) {
  const bar = document.getElementById('progress-bar');
  const textEl = document.getElementById('progress-text');
  bar.style.width = `${percent}%`;
  textEl.textContent = text || `${percent}%`;
}

function simulateProgress(duration = 3000) {
  let progress = 0;
  const steps = ['Subiendo archivo...', 'Leyendo Excel...', 'Procesando datos...', 'Aplicando filtros...', 'Finalizando...'];
  let stepIndex = 0;
  
  const interval = setInterval(() => {
    progress += Math.random() * 15 + 5; // Increment by 5-20%
    if (progress > 95) progress = 95; // Don't complete until real response
    
    const currentStep = Math.floor((progress / 100) * steps.length);
    if (currentStep < steps.length && currentStep !== stepIndex) {
      stepIndex = currentStep;
    }
    
    updateProgress(Math.floor(progress), steps[stepIndex] || 'Procesando...');
    
    if (progress >= 95) {
      clearInterval(interval);
    }
  }, duration / 20);
  
  return interval;
}

window.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('upload-form');
  const fileInput = document.getElementById('file');
  const selLinea = document.getElementById('filter-linea');
  const selCliente = document.getElementById('filter-cliente');
  const selProducto = document.getElementById('filter-producto');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const file = fileInput.files[0];
    if (!file) {
      setStatus('Seleccione un archivo Excel primero', 'danger');
      return;
    }
    
    // Show file size info
    const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
    setStatus(`Preparando archivo (${sizeMB} MB)...`, 'primary');
    
    const fd = new FormData();
    fd.append('file', file);
    
    // Start progress simulation
    showProgress(true);
    const progressInterval = simulateProgress(4000);
    
    try {
      const res = await fetch('/upload', { method: 'POST', body: fd });
      
      // Clear simulation and show completion
      clearInterval(progressInterval);
      updateProgress(100, 'Completado');
      
      const isJson = (res.headers.get('content-type') || '').includes('application/json');
      let data = null;
      if (isJson) {
        try { data = await res.json(); } catch (_) { /* ignore JSON parse error */ }
      }
      
      if (!res.ok) {
        showProgress(false);
        if (res.status === 413) {
          setStatus((data && data.error) || 'El archivo excede el tamaño máximo permitido (50MB).', 'danger');
        } else {
          const txt = isJson ? (data && data.error) : (await res.text());
          setStatus(txt || 'Error al procesar', 'danger');
        }
        return;
      }
      
      if (!isJson) {
        showProgress(false);
        setStatus('Respuesta del servidor no válida (no JSON).', 'danger');
        return;
      }
      
      // Success - hide progress and show results
      setTimeout(() => showProgress(false), 1000); // Keep progress visible briefly
      setStatus(`${data.message || 'Archivo procesado'} (${data.count || 0} contratos encontrados)`, 'success');
      
      // Fill filters
      fillSelect(selLinea, data.filters?.lineas || [], 'Todas');
      fillSelect(selCliente, data.filters?.clientes || [], 'Todos');
      fillSelect(selProducto, data.filters?.productos || [], 'Todas');
      
      // Render initial
      renderChart(data.buckets || {});
      renderSoonest(data.soonest || []);
      
      // Fetch records to fill table
      await fetchDataWithFilters();
      
    } catch (err) {
      clearInterval(progressInterval);
      showProgress(false);
      console.error(err);
      setStatus('Error de red o de servidor', 'danger');
    }
  });

  selLinea.addEventListener('change', fetchDataWithFilters);
  selCliente.addEventListener('change', fetchDataWithFilters);
  selProducto.addEventListener('change', fetchDataWithFilters);
});
