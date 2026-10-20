def _analytics_html() -> str:
    return """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Upstash Analytics | x402</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #09090b; color: #fafafa; font-family: ui-sans-serif, system-ui, sans-serif; }
        .card { background: #18181b; border: 1px solid #27272a; border-radius: 0.75rem; padding: 1.5rem; }
    </style>
</head>
<body class="p-8">
    <div class="max-w-6xl mx-auto space-y-6">
        <div class="flex items-center justify-between">
            <div>
                <h1 class="text-3xl font-extrabold tracking-tight">Real-Time Analytics</h1>
                <p class="text-zinc-400 mt-1">Powered by Upstash Redis Streams</p>
            </div>
            <div class="text-right">
                <div class="text-xs text-zinc-500 uppercase tracking-widest font-semibold mb-1">Total API Hits</div>
                <div class="text-4xl font-black text-emerald-400" id="total-hits">0</div>
            </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="card">
                <h2 class="text-lg font-semibold mb-4">Endpoint Distribution</h2>
                <canvas id="endpointsChart"></canvas>
            </div>
            <div class="card">
                <h2 class="text-lg font-semibold mb-4">HTTP Status Codes</h2>
                <canvas id="statusChart"></canvas>
            </div>
        </div>
    </div>

    <script>
        const ctxEndpoints = document.getElementById('endpointsChart').getContext('2d');
        const ctxStatus = document.getElementById('statusChart').getContext('2d');

        const chartOptions = {
            responsive: true,
            plugins: { legend: { position: 'bottom', labels: { color: '#a1a1aa' } } }
        };

        let endpointsChart = new Chart(ctxEndpoints, {
            type: 'doughnut',
            data: { labels: [], datasets: [{ data: [], backgroundColor: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6'] }] },
            options: chartOptions
        });

        let statusChart = new Chart(ctxStatus, {
            type: 'bar',
            data: { labels: [], datasets: [{ label: 'Responses', data: [], backgroundColor: '#6366f1' }] },
            options: { ...chartOptions, scales: { y: { beginAtZero: true, grid: { color: '#27272a' }, ticks: { color: '#a1a1aa' } }, x: { grid: { display: false }, ticks: { color: '#a1a1aa' } } } }
        });

        async function fetchAnalytics() {
            try {
                const res = await fetch('/analytics');
                const data = await res.json();
                
                if(data.error) return;

                document.getElementById('total-hits').textContent = data.total_hits.toLocaleString();

                // Update Endpoints
                const epKeys = Object.keys(data.endpoints).sort((a,b) => data.endpoints[b] - data.endpoints[a]).slice(0, 5);
                endpointsChart.data.labels = epKeys;
                endpointsChart.data.datasets[0].data = epKeys.map(k => data.endpoints[k]);
                endpointsChart.update();

                // Update Status Codes
                const statusKeys = Object.keys(data.status_codes);
                statusChart.data.labels = statusKeys;
                statusChart.data.datasets[0].data = statusKeys.map(k => data.status_codes[k]);
                statusChart.update();

            } catch (err) {
                console.error(err);
            }
        }

        fetchAnalytics();
        setInterval(fetchAnalytics, 2000);
    </script>
</body>
</html>
"""
