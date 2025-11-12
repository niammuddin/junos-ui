(function () {
    const config = window.interfaceTrafficConfig || {};
    if (!config.endpoints) {
        console.warn('Interface traffic config missing endpoints');
        return;
    }

    const state = {
        isMonitoring: false,
        timerId: null,
        currentFilter: 'all',
        updateIntervalMs: 10000,
        trafficData: {},
        maxChartPoints: 20,
    };

    const elements = {};
    const charts = {
        traffic: null,
        packets: null,
    };

    document.addEventListener('DOMContentLoaded', init);

    function init() {
        elements.interfaceSelect = document.getElementById('interfaceSelect');
        elements.intervalSelect = document.getElementById('intervalSelect');
        elements.viewSelect = document.getElementById('viewSelect');
        elements.startBtn = document.getElementById('startBtn');
        elements.stopBtn = document.getElementById('stopBtn');
        elements.connectionStatus = document.getElementById('connectionStatus');
        elements.tableView = document.getElementById('tableView');
        elements.chartsView = document.getElementById('chartsView');
        elements.trafficTableBody = document.getElementById('trafficTableBody');
        elements.lastUpdate = document.getElementById('lastUpdate');
        elements.totalInRate = document.getElementById('totalInRate');
        elements.totalOutRate = document.getElementById('totalOutRate');
        elements.totalPps = document.getElementById('totalPps');
        elements.activeInterfaces = document.getElementById('activeInterfaces');

        if (!elements.startBtn) {
            console.warn('Interface traffic elements not found; aborting init');
            return;
        }

        elements.startBtn.addEventListener('click', onStartClicked);
        elements.stopBtn.addEventListener('click', onStopClicked);
        elements.viewSelect.addEventListener('change', () => applyView(elements.viewSelect.value));

        loadInterfaces();
        initializeCharts();
        applyView(elements.viewSelect.value);
        setStatus('Ready to start monitoring');
    }

    async function loadInterfaces() {
        try {
            const response = await fetch(config.endpoints.interfaces);
            const data = await response.json();

            if (!data.success) {
                console.warn('Failed to load interfaces:', data.message);
                setStatus(data.message || 'Gagal memuat daftar interface');
                return;
            }

            populateInterfaceOptions(data.interfaces || []);
        } catch (error) {
            console.error('Error loading interfaces:', error);
            setStatus('Gagal memuat daftar interface');
        }
    }

    function populateInterfaceOptions(interfaces) {
        if (!elements.interfaceSelect) return;
        while (elements.interfaceSelect.options.length > 1) {
            elements.interfaceSelect.remove(1);
        }

        interfaces
            .filter(iface => !iface.disabled)
            .forEach(iface => {
                const option = document.createElement('option');
                option.value = iface.name;

                const parts = [iface.name];
                if (iface.description) {
                    parts.push(`- ${iface.description}`);
                }
                if (iface.type) {
                    parts.push(`(${iface.type})`);
                }

                option.textContent = parts.join(' ');
                elements.interfaceSelect.appendChild(option);
            });
    }

    async function onStartClicked() {
        if (state.isMonitoring) {
            return;
        }

        state.currentFilter = elements.interfaceSelect.value || 'all';
        const intervalSeconds = parseInt(elements.intervalSelect.value, 10) || 10;
        state.updateIntervalMs = Math.max(intervalSeconds, 1) * 1000;

        toggleButtons(true);
        setStatus('Starting monitoring...');

        try {
            const response = await fetch(config.endpoints.start, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    interface: state.currentFilter,
                    interval_seconds: intervalSeconds,
                }),
            });

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to start monitoring');
            }

            state.isMonitoring = true;
            scheduleUpdates();
            await updateTrafficData();
            setStatus(data.message || 'Monitoring started');
        } catch (error) {
            console.error('Unable to start monitoring:', error);
            setStatus(`Failed to start monitoring: ${error.message}`);
            toggleButtons(false);
        }
    }

    async function onStopClicked() {
        if (!state.isMonitoring) {
            return;
        }

        clearInterval(state.timerId);
        state.timerId = null;
        state.isMonitoring = false;
        toggleButtons(false);

        try {
            const response = await fetch(config.endpoints.stop, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            const data = await response.json();
            setStatus(data.message || 'Monitoring stopped');
        } catch (error) {
            console.error('Unable to stop monitoring:', error);
            setStatus('Monitoring stopped (local)');
        }
    }

    function scheduleUpdates() {
        clearInterval(state.timerId);
        state.timerId = setInterval(() => {
            updateTrafficData().catch(error => {
                console.error('Update failed:', error);
                setStatus('Error fetching data');
            });
        }, state.updateIntervalMs);
    }

    async function updateTrafficData() {
        const url = new URL(config.endpoints.update, window.location.origin);
        url.searchParams.set('interface', state.currentFilter || 'all');

        const response = await fetch(url);
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.message || 'Update failed');
        }

        state.trafficData = data.traffic || {};
        elements.lastUpdate.textContent = `Last update: ${new Date().toLocaleTimeString()}`;

        updateTrafficTable();
        updateSummaryStats();
        updateCharts();
    }

    function updateTrafficTable() {
        const tbody = elements.trafficTableBody;
        if (!tbody) {
            return;
        }
        tbody.innerHTML = '';

        const entries = Object.entries(state.trafficData);
        if (entries.length === 0) {
            const row = document.createElement('tr');
            row.innerHTML = '<td colspan="8" class="text-center text-muted">No traffic data available</td>';
            tbody.appendChild(row);
            return;
        }

        entries.forEach(([iface, data]) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${iface}</strong></td>
                <td><span class="badge bg-success">Active</span></td>
                <td>${formatBits(data.in_rate)}</td>
                <td>${formatBits(data.out_rate)}</td>
                <td>${formatPackets(data.in_pps)}</td>
                <td>${formatPackets(data.out_pps)}</td>
                <td>${renderUtilization(data.in_rate + data.out_rate)}</td>
                <td>📈</td>
            `;
            tbody.appendChild(row);
        });
    }

    function updateSummaryStats() {
        let totalIn = 0;
        let totalOut = 0;
        let totalPps = 0;
        let activeCount = 0;

        Object.values(state.trafficData).forEach(data => {
            totalIn += data.in_rate || 0;
            totalOut += data.out_rate || 0;
            totalPps += (data.in_pps || 0) + (data.out_pps || 0);
            activeCount += 1;
        });

        elements.totalInRate.textContent = formatBits(totalIn);
        elements.totalOutRate.textContent = formatBits(totalOut);
        elements.totalPps.textContent = formatPackets(totalPps);
        elements.activeInterfaces.textContent = activeCount.toString();

        state.totals = { totalIn, totalOut, totalInPps: totalPps / 2, totalOutPps: totalPps / 2 };
    }

    function initializeCharts() {
        const trafficCtx = document.getElementById('trafficChart');
        const packetsCtx = document.getElementById('packetsChart');

        if (!trafficCtx || !packetsCtx || typeof Chart === 'undefined') {
            console.warn('Chart.js context not available');
            return;
        }

        charts.traffic = new Chart(trafficCtx.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Ingress (Mbps)',
                        data: [],
                        borderColor: '#0d6efd',
                        fill: false,
                        tension: 0.25,
                    },
                    {
                        label: 'Egress (Mbps)',
                        data: [],
                        borderColor: '#20c997',
                        fill: false,
                        tension: 0.25,
                    },
                ],
            },
            options: chartOptions('Mbps'),
        });

        charts.packets = new Chart(packetsCtx.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Ingress (pps)',
                        data: [],
                        borderColor: '#ffc107',
                        fill: false,
                        tension: 0.25,
                    },
                    {
                        label: 'Egress (pps)',
                        data: [],
                        borderColor: '#fd7e14',
                        fill: false,
                        tension: 0.25,
                    },
                ],
            },
            options: chartOptions('pps'),
        });
    }

    function updateCharts() {
        if (!charts.traffic || !charts.packets || !state.totals) {
            return;
        }

        const label = new Date().toLocaleTimeString();
        const ingressMbps = state.totals.totalIn / 1_000_000;
        const egressMbps = state.totals.totalOut / 1_000_000;

        const ingressPps = Object.values(state.trafficData).reduce((sum, data) => sum + (data.in_pps || 0), 0);
        const egressPps = Object.values(state.trafficData).reduce((sum, data) => sum + (data.out_pps || 0), 0);

        pushChartData(charts.traffic, label, [ingressMbps, egressMbps]);
        pushChartData(charts.packets, label, [ingressPps, egressPps]);
    }

    function pushChartData(chart, label, values) {
        if (!chart) return;

        chart.data.labels.push(label);
        values.forEach((value, index) => {
            if (!chart.data.datasets[index]) return;
            chart.data.datasets[index].data.push(Number(value.toFixed ? value.toFixed(2) : value));
        });

        if (chart.data.labels.length > state.maxChartPoints) {
            chart.data.labels.shift();
            chart.data.datasets.forEach(dataset => dataset.data.shift());
        }

        chart.update('none');
    }

    function chartOptions(suffix) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${ctx.formattedValue} ${suffix}`,
                    },
                },
            },
            scales: {
                y: {
                    ticks: {
                        callback: value => `${value} ${suffix}`,
                    },
                },
            },
        };
    }

    function renderUtilization(totalRate) {
        const maxCapacity = 1_000_000_000; // Assume 1Gbps by default
        const utilization = Math.min((totalRate / maxCapacity) * 100, 100);
        const barClass = utilization > 80 ? 'bg-danger' : utilization > 50 ? 'bg-warning' : 'bg-success';

        return `
            <div class="progress" style="height: 10px;">
                <div class="progress-bar ${barClass}" style="width: ${utilization.toFixed(1)}%"></div>
            </div>
        `;
    }

    function toggleButtons(isMonitoring) {
        elements.startBtn.classList.toggle('d-none', isMonitoring);
        elements.stopBtn.classList.toggle('d-none', !isMonitoring);
    }

    function applyView(view) {
        const showTable = view === 'table' || view === 'both';
        const showCharts = view === 'charts' || view === 'both';

        if (elements.tableView) {
            elements.tableView.classList.toggle('d-none', !showTable);
        }
        if (elements.chartsView) {
            elements.chartsView.classList.toggle('d-none', !showCharts);
        }
    }

    function setStatus(message) {
        if (elements.connectionStatus) {
            elements.connectionStatus.textContent = message;
        }
    }

    function formatBits(bits = 0) {
        if (bits >= 1_000_000_000) return `${(bits / 1_000_000_000).toFixed(2)} Gbps`;
        if (bits >= 1_000_000) return `${(bits / 1_000_000).toFixed(2)} Mbps`;
        if (bits >= 1_000) return `${(bits / 1_000).toFixed(2)} Kbps`;
        return `${Math.round(bits)} bps`;
    }

    function formatPackets(value = 0) {
        return `${Number(value).toLocaleString()} pps`;
    }
})();
