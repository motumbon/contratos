// Global state for filters
let activeFilters = {
  lineas: [],
  clientes: [],
  productos: [],
  dateRange: null
};

// Helper: populate checkbox filters
function fillCheckboxFilter(containerId, items, filterType) {
  const container = document.getElementById(containerId);
  if (!items || items.length === 0) {
    container.innerHTML = '<div class="text-muted small" style="color: #e2e8f0 !important;">Sin opciones</div>';
    return;
  }
  
  container.innerHTML = '';
  for (const item of items) {
    const div = document.createElement('div');
    div.className = 'form-check';
    div.innerHTML = `
      <input class="form-check-input" type="checkbox" value="${item}" id="${filterType}-${item.replace(/[^a-zA-Z0-9]/g, '')}" data-filter-type="${filterType}">
      <label class="form-check-label small" for="${filterType}-${item.replace(/[^a-zA-Z0-9]/g, '')}" title="${item}">
        ${item.length > 30 ? item.substring(0, 30) + '...' : item}
      </label>
    `;
    container.appendChild(div);
  }
  
  // Add event listeners to checkboxes
  container.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
    checkbox.addEventListener('change', handleFilterChange);
  });
}

function getContractTypeBadge(tipo) {
  if (!tipo) return '<span class="badge bg-secondary">-</span>';
  
  const tipoLower = tipo.toLowerCase();
  let badgeClass = 'bg-secondary';
  
  if (tipoLower.includes('licitacion publica') || tipoLower.includes('licitación pública')) {
    badgeClass = 'bg-success'; // Verde
  } else if (tipoLower.includes('trato directo')) {
    badgeClass = 'bg-warning'; // Naranja/Amarillo
  } else if (tipoLower.includes('acuerdo comercial')) {
    badgeClass = 'bg-primary'; // Azul
  } else if (tipoLower.includes('cotizacion masiva') || tipoLower.includes('cotización masiva')) {
    badgeClass = 'bg-danger'; // Rojo
  } else if (tipoLower.includes('cotizacion') || tipoLower.includes('cotización')) {
    badgeClass = 'bg-info'; // Azul claro/Cian
  } else if (tipoLower.includes('licitacion privada') || tipoLower.includes('licitación privada')) {
    badgeClass = 'bg-dark'; // Gris oscuro
  }
  
  return `<span class="badge ${badgeClass}">${tipo}</span>`;
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
      <td>${getContractTypeBadge(r['Tipo Ctto'])}</td>
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
  const colors = ['#dc3545', '#ffc107', '#fd7e14', '#0dcaf0', '#198754'];
  
  // Highlight selected range
  const highlightColors = colors.map((color, i) => {
    const range = ['vencidos', '0-30', '31-60', '61-90', '90+'][i];
    return activeFilters.dateRange === range ? color : color + '80'; // Add transparency if not selected
  });
  
  const data = [{
    x: labels,
    y: values,
    type: 'bar',
    marker: { 
      color: activeFilters.dateRange ? highlightColors : colors,
      line: { width: 2, color: '#fff' }
    },
    hovertemplate: '<b>%{x}</b><br>Contratos: %{y}<br><i>Click para filtrar</i><extra></extra>'
  }];
  
  const layout = {
    margin: { t: 10, r: 10, l: 40, b: 40 },
    yaxis: { 
      title: { text: 'Cantidad', font: { color: '#e2e8f0', size: 12 } },
      tickfont: { color: '#cbd5e0', size: 10 },
      gridcolor: '#4a5568'
    },
    xaxis: { 
      title: { text: 'Rango de vencimiento', font: { color: '#e2e8f0', size: 12 } },
      tickfont: { color: '#cbd5e0', size: 10 },
      gridcolor: '#4a5568'
    },
    plot_bgcolor: '#1a202c',
    paper_bgcolor: '#2d3748',
    font: { color: '#e2e8f0' }
  };
  
  const config = {
    displayModeBar: false, 
    responsive: true,
    staticPlot: false
  };
  
  Plotly.newPlot('chart', data, layout, config);
  
  // Add click event to bars
  document.getElementById('chart').on('plotly_click', function(data) {
    const pointIndex = data.points[0].pointIndex;
    const ranges = ['vencidos', '0-30', '31-60', '61-90', '90+'];
    const selectedRange = ranges[pointIndex];
    
    // Toggle date range filter
    if (activeFilters.dateRange === selectedRange) {
      activeFilters.dateRange = null; // Deselect if already selected
    } else {
      activeFilters.dateRange = selectedRange;
    }
    
    updateActiveFiltersDisplay();
    fetchDataWithFilters();
  });
}

function renderSoonest(soonest) {
  const list = document.getElementById('soonest-list');
  list.innerHTML = '';
  for (const r of soonest || []) {
    const li = document.createElement('li');
    li.className = 'list-group-item d-flex justify-content-between align-items-start';
    li.style.cursor = 'pointer'; // Indicar que es clickeable
    li.title = 'Haz clic para filtrar por este contrato'; // Tooltip
    
    const content = document.createElement('div');
    content.className = 'ms-2 me-auto';
    content.innerHTML = `<div class="d-flex justify-content-between align-items-center" style="gap: 2rem;">
        <span class="fw-semibold">${r['Nom_Cliente'] ?? ''}</span>
        <span class="fw-semibold text-white">Contrato: ${r['Nº de pedido'] ?? ''}</span>
      </div>
      <div class="small text-muted">Fin: ${r['Fin de validez'] ?? ''}</div>`;
    
    // Agregar evento de clic para filtrar por este contrato
    li.addEventListener('click', () => {
      filterByContract(r['Nom_Cliente'], r['Nº de pedido']);
    });
    
    li.appendChild(content);
    list.appendChild(li);
  }
}

function handleFilterChange(event) {
  const checkbox = event.target;
  const filterType = checkbox.dataset.filterType;
  const value = checkbox.value;
  
  if (checkbox.checked) {
    if (!activeFilters[filterType].includes(value)) {
      activeFilters[filterType].push(value);
    }
  } else {
    activeFilters[filterType] = activeFilters[filterType].filter(v => v !== value);
  }
  
  updateActiveFiltersDisplay();
  fetchDataWithFilters();
}

function updateActiveFiltersDisplay() {
  const activeFiltersEl = document.getElementById('active-filters');
  const activeFiltersText = document.getElementById('active-filters-text');
  
  const filterTexts = [];
  
  if (activeFilters.lineas.length > 0) {
    filterTexts.push(`Líneas: ${activeFilters.lineas.length}`);
  }
  if (activeFilters.clientes.length > 0) {
    filterTexts.push(`Clientes: ${activeFilters.clientes.length}`);
  }
  if (activeFilters.productos.length > 0) {
    filterTexts.push(`Productos: ${activeFilters.productos.length}`);
  }
  if (activeFilters.dateRange) {
    const rangeNames = {
      'vencidos': 'Vencidos',
      '0-30': '0-30 días',
      '31-60': '31-60 días', 
      '61-90': '61-90 días',
      '90+': '90+ días'
    };
    filterTexts.push(`Rango: ${rangeNames[activeFilters.dateRange]}`);
  }
  
  if (filterTexts.length > 0) {
    activeFiltersText.textContent = filterTexts.join(' | ');
    activeFiltersEl.style.display = 'block';
  } else {
    activeFiltersEl.style.display = 'none';
  }
}

function filterByContract(cliente, pedido) {
  // Limpiar filtros existentes
  activeFilters = {
    lineas: [],
    clientes: [],
    productos: [],
    dateRange: null
  };
  
  // Desmarcar todos los checkboxes
  document.querySelectorAll('input[type="checkbox"][data-filter-type]').forEach(cb => {
    cb.checked = false;
  });
  
  // Aplicar filtro específico por cliente
  if (cliente) {
    activeFilters.clientes = [cliente];
    // Marcar el checkbox correspondiente si existe
    const clienteCheckbox = document.querySelector(`input[data-filter-type="clientes"][value="${cliente}"]`);
    if (clienteCheckbox) {
      clienteCheckbox.checked = true;
    }
  }
  
  // Filtrar directamente la tabla por cliente y pedido
  filterTableByContract(cliente, pedido);
  
  updateActiveFiltersDisplay();
}

function filterTableByContract(cliente, pedido) {
  // Obtener todos los registros de la sesión
  fetch('/data')
    .then(res => res.json())
    .then(data => {
      const records = data.records || [];
      
      // Filtrar por cliente y pedido específico
      const filtered = records.filter(r => {
        const matchCliente = !cliente || r['Nom_Cliente'] === cliente;
        const matchPedido = !pedido || r['Nº de pedido'] === pedido;
        return matchCliente && matchPedido;
      });
      
      // Actualizar solo la tabla (no los gráficos ni próximos vencimientos)
      renderTable(filtered);
      
      // Mostrar mensaje informativo
      if (filtered.length > 0) {
        setStatus(`Mostrando ${filtered.length} registros para ${cliente} - Pedido: ${pedido}`, 'info');
      } else {
        setStatus(`No se encontraron registros para ${cliente} - Pedido: ${pedido}`, 'warning');
      }
    })
    .catch(error => {
      console.error('Error filtering by contract:', error);
      setStatus('Error al filtrar por contrato', 'danger');
    });
}

function clearAllFilters() {
  // Reset filter state
  activeFilters = {
    lineas: [],
    clientes: [],
    productos: [],
    dateRange: null
  };
  
  // Uncheck all checkboxes
  document.querySelectorAll('input[type="checkbox"][data-filter-type]').forEach(cb => {
    cb.checked = false;
  });
  
  updateActiveFiltersDisplay();
  fetchDataWithFilters();
}

async function fetchDataWithFilters() {
  const params = new URLSearchParams();
  
  // Add multiple values for each filter type
  activeFilters.lineas.forEach(linea => params.append('linea', linea));
  activeFilters.clientes.forEach(cliente => params.append('cliente', cliente));
  activeFilters.productos.forEach(producto => params.append('producto', producto));
  
  if (activeFilters.dateRange) {
    params.set('date_range', activeFilters.dateRange);
  }
  
  try {
    const res = await fetch('/data' + (params.toString() ? ('?' + params.toString()) : ''));
    if (!res.ok) {
      console.error('Error cargando datos con filtros');
      return;
    }
    const data = await res.json();
    renderTable(data.records || []);
    renderChart(data.buckets || {});
    renderSoonest(data.soonest || []);
  } catch (error) {
    console.error('Error fetching filtered data:', error);
  }
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
  const clearFiltersBtn = document.getElementById('clear-filters');

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
      
      // Fill checkbox filters
      fillCheckboxFilter('filter-linea-container', data.filters?.lineas || [], 'lineas');
      fillCheckboxFilter('filter-cliente-container', data.filters?.clientes || [], 'clientes');
      fillCheckboxFilter('filter-producto-container', data.filters?.productos || [], 'productos');
      
      // Reset filter state
      activeFilters = {
        lineas: [],
        clientes: [],
        productos: [],
        dateRange: null
      };
      
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

  // Clear filters button
  clearFiltersBtn.addEventListener('click', clearAllFilters);
});
