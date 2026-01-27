class PipelineManager {
    constructor() {
        this.chart = null;
    }

    async init() {
        try {
            const response = await fetch('/api/dashboard/stats');
            const data = await response.json();

            if (data.pipeline) {
                this.renderChart(data.pipeline);
                this.renderFunnel(data.pipeline);
            }
        } catch (error) {
            console.error('Pipeline Init Error:', error);
        }
    }

    /* ------------------------------------------------
       1. Doughnut Chart
    ------------------------------------------------ */
    renderChart(pipeline) {
        const ctx = document.getElementById('pipelineChart');
        if (!ctx) return;

        // Destroy previous instance
        if (this.chart) {
            this.chart.destroy();
        }

        const stages = ['New', 'Attempted', 'Connected', 'Converted', 'Won'];
        const values = stages.map(s => pipeline[s] || 0);

        this.chart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: stages,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        '#3b82f6', // Blue-500
                        '#f59e0b', // Amber-500
                        '#6366f1', // Indigo-500
                        '#14b8a6', // Teal-500
                        '#10b981'  // Emerald-500
                    ],
                    borderWidth: 0,
                    hoverOffset: 15
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '75%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            usePointStyle: true,
                            padding: 20,
                            font: { family: 'Inter', size: 12 }
                        }
                    }
                }
            }
        });
    }

    /* ------------------------------------------------
       2. Sales Funnel - High Fidelity 3D Design
    ------------------------------------------------ */
    renderFunnel(pipeline) {
        const container = document.getElementById('funnel-container');
        if (!container) return;

        // Stage Configuration (Mockup Alignment)
        const stages = [
            {
                key: 'New',
                color: 'from-blue-600 to-blue-400',
                top: 100, bottom: 85,
                icon: 'fa-bullhorn',
                label: 'AWARENESS'
            },
            {
                key: 'Attempted',
                color: 'from-amber-500 to-amber-400',
                top: 85, bottom: 72,
                icon: 'fa-lightbulb',
                label: 'INTEREST'
            },
            {
                key: 'Connected',
                color: 'from-indigo-600 to-indigo-500',
                top: 72, bottom: 59,
                icon: 'fa-handshake',
                label: 'CONSIDERATION'
            },
            {
                key: 'Converted',
                color: 'from-teal-500 to-teal-400',
                top: 59, bottom: 46,
                icon: 'fa-file-alt',
                label: 'INTENT'
            },
            {
                key: 'Won',
                color: 'from-emerald-500 to-emerald-400',
                top: 46, bottom: 46,
                icon: 'fa-shopping-cart',
                label: 'PURCHASE'
            }
        ];

        // Generate the 3D Connected Funnel
        container.innerHTML = `
            <div class="w-full flex flex-col items-center py-8">
                ${stages.map((stage, index) => {
            const count = pipeline[stage.key] || 0;

            // Trapezoid Geometry
            const t1 = (100 - stage.top) / 2;
            const t2 = 100 - t1;
            const b1 = (100 - stage.bottom) / 2;
            const b2 = 100 - b1;

            return `
                        <div class="relative w-full -mb-1 group cursor-default h-[70px]" style="max-width: 500px;">
                            <!-- The Trapezoid Segment -->
                            <div class="absolute inset-0 bg-gradient-to-r ${stage.color} shadow-lg transition-transform duration-300 transform group-hover:scale-[1.02] active:scale-[0.98]"
                                 style="clip-path: polygon(${t1}% 0%, ${t2}% 0%, ${b2}% 100%, ${b1}% 100%); z-index: ${10 - index};">
                                
                                <!-- Bevel Effect -->
                                <div class="absolute inset-0 opacity-20 bg-gradient-to-b from-white to-transparent h-[4px]"></div>
                                
                                <!-- Content Layer -->
                                <div class="h-full flex items-center justify-between px-[18%] text-white">
                                    <div class="flex items-center gap-3">
                                        <i class="fas ${stage.icon} text-lg opacity-80"></i>
                                        <div class="flex flex-col">
                                            <span class="text-[9px] font-bold opacity-60 tracking-widest leading-none">${stage.label}</span>
                                            <span class="text-sm font-bold tracking-wide">${stage.key}</span>
                                        </div>
                                    </div>
                                    
                                    <!-- Frosted Glass Badge -->
                                    <div class="bg-white bg-opacity-20 backdrop-blur-md px-4 py-1.5 rounded-full border border-white border-opacity-30 flex items-center shadow-inner">
                                        <span class="text-sm font-black">${count.toLocaleString()}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
        }).join('')}
            </div>
        `;
    }
}

// Global scope initialization handled by the app
window.pipelineManager = new PipelineManager();
