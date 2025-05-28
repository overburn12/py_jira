const ctx = document.getElementById('timeline-chart').getContext('2d');
let timelineChart = null;

document.getElementById('load-button').addEventListener('click', async () => {
    const rtValue = rtSelect.value;;
    const infoDisplay = document.getElementById('chart-info');

    try {
        const response = await fetch(`/api/get_timeline?rt=${rtValue}`);
        const data_raw = await response.json();

        window.timeline = data_raw.timeline;
        window.epic_key = data_raw.rt;

        const selectedRadioButton = document.querySelector('input[name="radio-group"]:checked');
        if (selectedRadioButton.value === "Changes") {
            data = formatTimelineForChartjsDelta(data_raw);
        } else {
            data = formatTimelineForChartjs(data_raw);
        }
        
        // Clear old chart if it exists
        if (timelineChart) {
            timelineChart.destroy();
        }

        if (data === null){
            alert("No data for order");
            return;
        }

        infoDisplay.innerHTML = ''; //reset the serial list display
        renderChart(data);


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


function formatTimelineForChartjsDelta(epicData) {
    const timeline = epicData.timeline;

    if (timeline === null) {
        return null;
    }

    const labels = Object.keys(timeline).sort();
    const allStatuses = Object.keys(timeline[labels[0]]);

    const datasets = allStatuses.map(status => {
        let prev = null;
        const data = labels.map(day => {
            const count = timeline[day][status]?.length ?? 0;
            const delta = prev === null ? 0 : count - prev;
            prev = count;
            return delta;
        });
        return {
            label: status,
            data: data
        };
    });

    return {
        labels: labels,
        datasets: datasets,
        title: epicData.title + " (Daily Delta)"
    };
}


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
    "Total Boards": "black",
    "Total Chassis": "rgb(105, 105, 0)",
    "Ready to Ship": "yellow"
};


//random color for statuses that dont fit status-to-color map
function getRandomColor() {
    const r = Math.floor(Math.random() * 256);
    const g = Math.floor(Math.random() * 256);
    const b = Math.floor(Math.random() * 256);
    return `rgb(${r}, ${g}, ${b})`;
}

function toolTipCallBack(context) {
    const dataset = context.dataset;
    const index = context.dataIndex;
    const label = dataset.label || '';
    const current = context.parsed.y;

    const lines = [`${label}: ${current}`];

    const compareList = {
        'Total Processed': ['Scrap', 'Passed Initial Diagnosis', 'Awaiting Functional Test', 'Awaiting Advanced Repair', 'Total Good'],
        'Total Boards': ['Scrap', 'Passed Initial Diagnosis', 'Awaiting Functional Test', 'Awaiting Advanced Repair', 'Total Processed', 'Total Good'],
        'Max Total Boards': ['Scrap', 'Passed Initial Diagnosis', 'Awaiting Functional Test', 'Awaiting Advanced Repair', 'Total Processed', 'Total Good', 'Total Boards']
    };

    const chart = context.chart;

    // Cache max Total Boards for the index, if needed
    let maxTotalBoards = null;
    if (Object.keys(compareList).includes('Max Total Boards')) {
        const totalBoardsDataset = chart.data.datasets.find(ds => ds.label === 'Total Boards');
        if (totalBoardsDataset) {
            maxTotalBoards = Math.max(...totalBoardsDataset.data.filter(n => typeof n === 'number'));
        }
    }

    // Loop through compareList to find all references that compare to this label
    for (const [referenceLabel, targets] of Object.entries(compareList)) {
        if (targets.includes(label)) {
            let referenceValue = null;

            if (referenceLabel === 'Max Total Boards') {
                referenceValue = maxTotalBoards;
            } else {
                const refDataset = chart.data.datasets.find(ds => ds.label === referenceLabel);
                if (refDataset) {
                    referenceValue = refDataset.data[index];
                }
            }

            if (typeof referenceValue === 'number' && referenceValue !== 0) {
                const percent = ((current / referenceValue) * 100).toFixed(1);
                lines.push(`vs ${referenceLabel}: ${percent}%`);
            }
        }
    }

    // Optional: delta from previous point in same dataset
    const prev = index > 0 ? dataset.data[index - 1] : null;
    if (typeof prev === 'number') {
        const delta = current - prev;
        const sign = delta > 0 ? '+' : '';
        lines.push(`Change: ${sign}${delta}`);
    }

    return lines;
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
                        label: toolTipCallBack
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





function createHbString(hashboard) {
    if ('progress_update' in hashboard) {
        return `\nTotal Issues: ${hashboard.total}, Proccessing at: ${hashboard.current}\n`;
    }

    const initials = (author) =>
        author.split(/\s+/).map(word => word[0].toUpperCase()).join('');

    let answer = `\n${hashboard.serial} `;

    if ('board_model' in hashboard) {
        answer += `(${hashboard.board_model})`;
    }

    answer += `\n${hashboard.repair_summary}\n`;

    if ('linked_issues' in hashboard) {
        answer += `Linked Issues:\n${hashboard.linked_issues.join('\n')}\n`;
    }

    for (const event of hashboard.events) {
        const init = initials(event.author);
        if (event.type === "status_change") {
            if (event.to === "Advanced Repair") {
                answer += `${event.time} (${init}) ${event.to} (${event.length})\n`;
            } else {
                answer += `${event.time} (${init}) ${event.to}\n`;
            }
        } else if (event.type === "comment") {
            answer += `${event.time} (${init})     ${event.body}\n`;
        }
    }

    return answer;
}


function generateSerialList(dateStr, label) {
    const serials = {};
    for (let offset = -1; offset < 2; offset++) {
        serials[offset] = window.timeline[changeDay(dateStr, offset)]?.[label] || [];
    }

    function annotateSerials(baseList, offsetDirection, descriptor) {
        return baseList.map(serial => {
            const relatedLabel = findSerialLabel(changeDay(dateStr, offsetDirection), serial);
            return { serial, display: `${serial} - ${descriptor} ${relatedLabel}` };
        });
    }

    const removed_serials = annotateSerials(
        serials[-1].filter(x => !serials[0].includes(x)),
        0,
        'to'
    );

    const unchanged_serials = serials[0].filter(x => serials[-1].includes(x)).map(s => ({ serial: s, display: s }));

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

    // Create the summary text area
    const textArea = document.createElement('textarea');
    textArea.setAttribute('wrap', 'oft');
    textArea.setAttribute('rows', 20);
    textArea.style.width = '700px';
    textArea.style.margin = '10px';
    textArea.style.marginTop = '0px';
    textArea.style.padding = '5px';
    textArea.style.whiteSpace = 'pre'; 
    textArea.style.overflow = 'auto'; 
    
    // issue summary fetcher
    async function handleSerialClick(serial) {
        try {
            const res = await fetch('/api/get_issue_summary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 'serial': serial, 'epic-key': window.epic_key }),
            });

            const result = await res.json();
            if (result.error) throw new Error(result.error);

            textArea.value = createHbString(result);
        } catch (err) {
            textArea.value = `Error fetching summary: ${err.message}`;
        }
    }

    for (const { title, color, data } of diffConfig) {
        const wrapperDiv = document.createElement('div');
        wrapperDiv.className = 'serial-div';

        const header = document.createElement('h3');
        header.textContent = `${title} (${data.length})`;

        const select = document.createElement('select');
        select.style.color = color;
        select.setAttribute('multiple', true);
        select.setAttribute('size', 18);
        select.style.padding = '5px';
        select.style.width = '300px';

        data.forEach(({ serial, display }) => {
            const option = document.createElement('option');
            option.value = serial;
            option.textContent = display;
            select.appendChild(option);
        });

        // Fetch summary when selection changes
        select.addEventListener('change', (e) => {
            const selected = Array.from(e.target.selectedOptions)[0]; // only handle first one for now
            if (selected) {
                handleSerialClick(selected.value);
            }
        });

        wrapperDiv.append(header, document.createElement('br'), select);
        serialDivContainer.append(wrapperDiv);
    }

    const wrapperDiv = document.createElement('div');
    wrapperDiv.className = 'serial-div';

    const header = document.createElement('h3');
    header.textContent = "Issue Summary";

    wrapperDiv.append(header, document.createElement('br'), textArea);
    serialDivContainer.append(wrapperDiv);

    return serialDivContainer;
}
