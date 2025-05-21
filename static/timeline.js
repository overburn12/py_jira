//const rtSelect = document.getElementById('rt_number');
//const form = document.getElementById('rt-form');
const ctx = document.getElementById('timeline-chart').getContext('2d');
let timelineChart = null;

document.getElementById('load-button').addEventListener('click', async () => {
    const rtValue = rtSelect.value;;

    try {
        const response = await fetch(`/get_timeline?rt=${rtValue}`);
        const data_raw = await response.json();

        window.timeline = data_raw.timeline;
        data = formatTimelineForChartjs(data_raw);
        
        // Clear old chart if it exists
        if (timelineChart) {
            timelineChart.destroy();
        }

        if (data === null){
            alert("No data for order");
            return;
        }

        renderChart(data);

        //const infoDisplay = document.getElementById('chart-info');

        timelineChart.options.onClick = (event, elements) => {
            if (!elements.length) return;
        
            const point = elements[0];
            const datasetIndex = point.datasetIndex;
            const index = point.index;
        
            const dataset = timelineChart.data.datasets[datasetIndex];

            const label = dataset.label;
            const dateStr = timelineChart.data.labels[index];
            const yValue = dataset.data[index];
            
            const infoDisplay = document.getElementById('chart-info');

            infoDisplay.innerHTML = `<center><h2>${label}</h2></center>`;
            infoDisplay.append(generateSerialList(dateStr, label, yValue));
            
        };

    } catch (error) {
        console.error('Error fetching timeline:', error);
        alert(`Failed to fetch timeline data: ${error.message}`);
    }

});


function formatTimelineForChartjs(epicData) {
    const timeline = epicData.timeline;

    if (timeline === null){
        return null;
    }

    const labels = Object.keys(timeline).sort();
    const allStatuses = Object.keys(timeline[labels[0]]);
    const datasets = allStatuses.map(status => {
        return {
            "label": status,
            "data": labels.map(day => timeline[day][status]?.length?? null)
        };
    });

    return {
        "labels": labels,
        "datasets": datasets,
        "title": epicData.title
    };
}

//shift forwards or backwards on the date
function changeDay(day, direction) {
    const date = new Date(day);
    date.setDate(date.getDate() + direction);
    return date.toISOString().split('T')[0]; // Return in 'YYYY-MM-DD'
}

//highlight the weekends on the chart
function generateWeekendBoxes(dateLabels) {
    const annotations = [];
    let currentBox = null;

    dateLabels.forEach((dateStr, idx) => {
        const day = new Date(dateStr);
        const dayOfWeek = day.getUTCDay(); // Sunday=0, Saturday=6

        if (dayOfWeek === 6) { // Saturday
            // Start of weekend box (shift back 12 hours)
            const xMin = new Date(day.getTime() - (12-4) * 60 * 60 * 1000).toISOString();
            currentBox = {
                type: 'box',
                xMin: xMin,
                backgroundColor: 'rgba(200, 200, 200, 0.5)',
                borderWidth: 0
            };
        } else if (dayOfWeek === 0 && currentBox) { // Sunday
            // End of weekend box (shift forward 12 hours)
            const xMax = new Date(day.getTime() + (12+4) * 60 * 60 * 1000).toISOString();
            currentBox.xMax = xMax;
            annotations.push(currentBox);
            currentBox = null;
        }
    });

    return annotations;
}


// Status-to-color map
const statusColors = {
    "Backlog": "gray",
    "Passed Initial Diagnosis": "green",
    "Awaiting Advanced Repair": "lightblue",
    "Awaiting Functional Test": "blue",
    "Done": "darkgray",
    "Scrap": "red",
    "Hashboard Replacement Program": "orange",
    "Advanced Repair": "yellow",
    "Total Boards": "black"
};


//random color for statuses that dont fit status-to-color map
function getRandomColor() {
    const r = Math.floor(Math.random() * 256);
    const g = Math.floor(Math.random() * 256);
    const b = Math.floor(Math.random() * 256);
    return `rgb(${r}, ${g}, ${b})`;
}


function renderChart(data){

    // Extract labels and build datasets
    const labels = data.labels;
    const datasets = data.datasets.map(ds => {
        const color = statusColors[ds.label] || getRandomColor();
        return {
            label: ds.label,
            data: ds.data,
            borderColor: color,
            backgroundColor: color,
            fill: false,
            tension: 0.1
        };
    });

    // Build the chart
    timelineChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: data.title || `Timeline for RT ${data.title}`
                },
                legend: {
                    display: true,
                    position: 'top'
                },
                annotation: {
                    display: true,
                    annotations: generateWeekendBoxes(data.labels)
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const dataset = context.dataset;
                            const index = context.dataIndex;
                            const label = dataset.label || '';
                            const current = context.parsed.y;
                            const prev = index > 0 ? dataset.data[index - 1] : null;
                            const delta = prev !== null ? current - prev : null;
                            const sign = delta > 0 ? '+' : '';
                            const deltaText = delta !== null ? ` (${sign}${delta})` : '';

                            return `${label}: ${current}${deltaText}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'day'
                    },
                    title: {
                        display: true,
                        text: 'Date'
                    }
                },
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Count'
                    }
                }
            }
        }
    });     
}


function findSerialLabel(dateStr, serial) {
    const dayData = window.timeline[dateStr];
    if (!dayData) return "New Hashboard";

    for (const label in dayData) {
        const serials = dayData[label];
        if (Array.isArray(serials) && serials.includes(serial)) {
            return label;
        }
    }

    return "New Hashboard";
}


function generateSerialList(dateStr, label) {
    const serials = {};
    for (let offset = -1; offset < 2; offset++) {
        serials[offset] = window.timeline[changeDay(dateStr, offset)]?.[label] || [];
    }

    function annotateSerials(baseList, offsetDirection, descriptor) {
        return baseList.map(serial => {
            const relatedLabel = findSerialLabel(changeDay(dateStr, offsetDirection), serial);
            return `${serial} - ${descriptor} ${relatedLabel}`;
        });
    }

    const removed_serials = annotateSerials(
        serials[-1].filter(x => !serials[0].includes(x)),
        0,
        'to'
    );

    const unchanged_serials = serials[0].filter(x => serials[-1].includes(x));

    const added_serials = annotateSerials(
        serials[0].filter(x => !serials[-1].includes(x)),
        -1,
        'from'
    );

    const diffConfig = [
        { title: 'Removed Serials', color: 'red', data: removed_serials },
        { title: 'Unchanged Serials', color: 'black', data: unchanged_serials },
        { title: 'Added Serials', color: 'green', data: added_serials },
    ];

    const serialDivContainer = document.createElement('div');
    serialDivContainer.className = 'serial-div-container';

    for (const { title, color, data } of diffConfig) {
        const wrapperDiv = document.createElement('div');
        wrapperDiv.className = 'serial-div';

        const header = document.createElement('h3');
        header.textContent = title;

        const pre = document.createElement('pre');
        pre.style.color = color;
        pre.textContent = data.join('\n');

        wrapperDiv.append(header, document.createElement('br'), pre);
        serialDivContainer.append(wrapperDiv);
    }

    return serialDivContainer;
}



