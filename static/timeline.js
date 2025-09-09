const ctx = document.getElementById('timeline-chart').getContext('2d');
let timelineChart = null;
let currentOrderKey = null;

// Function to parse URL parameters
function getUrlParameter(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

// Auto-load order on page load
window.addEventListener('DOMContentLoaded', () => {
    const key = getUrlParameter('key');
    if (key) {
        currentOrderKey = key;
        loadTimelineData(key);
    }
});

// Function to check for duplicate serials
async function checkForDuplicates(epicKey) {
    try {
        const response = await fetch(`/api/get_duplicate_serials?epic_key=${epicKey}`);
        const duplicates = await response.json();
        
        const warningDiv = document.getElementById('duplicate-warning');
        const detailsTextarea = document.getElementById('duplicate-details');
        
        if (duplicates && duplicates.length > 0) {
            // Format duplicate information
            let duplicateText = `Found ${duplicates.length} duplicate serial number(s):\n\n`;
            
            duplicates.forEach((duplicate, index) => {
                duplicateText += `${index + 1}. Serial: "${duplicate.serial}"\n`;
                duplicateText += `   Issue Keys: ${duplicate.keys.join(', ')}\n\n`;
            });
            
            detailsTextarea.value = duplicateText;
            warningDiv.style.display = 'block';
        } else {
            warningDiv.style.display = 'none';
        }
    } catch (error) {
        console.error('Error checking for duplicates:', error);
        // Don't show warning on error - fail silently
    }
}

// Function to load timeline data
async function loadTimelineData(rtValue) {
    const infoDisplay = document.getElementById('chart-info');

    try {
        const response = await fetch(`/api/get_timeline?rt=${rtValue}`);
        const data_raw = await response.json();

        window.timeline = data_raw.timeline;
        window.epic_key = data_raw.rt;

        // Update the page header with the dynamic title
        const pageTitle = document.getElementById('page-title');
        if (pageTitle && data_raw.title) {
            pageTitle.textContent = data_raw.title;
        }

        // Check for duplicates after loading timeline data
        await checkForDuplicates(data_raw.rt);

        data = formatTimelineForChartjs(data_raw);
        
        // Clear old chart if it exists
        if (timelineChart) {
            timelineChart.destroy();
        }

        if (data === null){
            alert("No data for order");
            return;
        }

        infoDisplay.innerHTML = ''; //reset the serial list display
        await renderChart(data);

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
}


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


async function generateWeekendBoxes(dateLabels) {
    const annotations = [];
    
    // Fetch holidays from API
    let holidayList = ['2025-05-26']; // fallback
    try {
        const response = await fetch('/api/get_holidays');
        const data = await response.json();
        if (data.holidays && Array.isArray(data.holidays)) {
            holidayList = data.holidays;
        }
    } catch (error) {
        console.warn('Failed to fetch holidays, using fallback list:', error);
    }
    
    const holidaySet = new Set(holidayList); // for fast lookup
    let currentBox = null;

    dateLabels.forEach((dateStr, idx) => {
        const day = new Date(dateStr);
        const isoDate = day.toISOString().split('T')[0]; // YYYY-MM-DD
        const dayOfWeek = day.getUTCDay(); // Sunday=0, Saturday=6

        if (dayOfWeek === 6) { // Saturday
            // Look back to Friday
            const friday = new Date(day);
            friday.setUTCDate(day.getUTCDate() - 1);
            const isFridayHoliday = holidaySet.has(friday.toISOString().split('T')[0]);

            // Start weekend box: either normal Sat, or extend to Friday if holiday
            const shiftHours = isFridayHoliday ? 36 : 12;
            const xMin = new Date(day.getTime() - (shiftHours - 4) * 60 * 60 * 1000).toISOString();
            currentBox = {
                type: 'box',
                xMin,
                backgroundColor: 'rgba(200, 200, 200, 0.5)',
                borderWidth: 0
            };

        } else if (dayOfWeek === 0 && currentBox) { // Sunday
            // Look ahead to Monday
            const monday = new Date(day);
            monday.setUTCDate(day.getUTCDate() + 1);
            const isMondayHoliday = holidaySet.has(monday.toISOString().split('T')[0]);

            // End of weekend box
            const shiftHours = isMondayHoliday ? 36 : 12;
            const xMax = new Date(day.getTime() + (shiftHours + 4) * 60 * 60 * 1000).toISOString();
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

    const delta = index > 0 && typeof dataset.data[index - 1] === 'number'
        ? current - dataset.data[index - 1]
        : null;
    const sign = delta !== null && delta > 0 ? '+' : '-';

    const lines = [
        `${label}: ${current}${delta !== null && delta !== 0 ? ` (${sign}${Math.abs(delta)})` : ''}`
    ];

    const compareList = {
        'Total Processed': ['Scrap', 'Passed Initial Diagnosis', 'Awaiting Functional Test', 'Total Good'],
        'Total Boards': ['Scrap', 'Passed Initial Diagnosis', 'Awaiting Functional Test', 'Awaiting Advanced Repair', 'Total Processed', 'Total Good'],
        'Max Total Boards': ['Scrap', 'Passed Initial Diagnosis', 'Awaiting Functional Test', 'Awaiting Advanced Repair', 'Total Processed', 'Total Good', 'Total Boards']
    };

    const chart = context.chart;

    let maxTotalBoards = null;
    if (Object.keys(compareList).includes('Max Total Boards')) {
        const totalBoardsDataset = chart.data.datasets.find(ds => ds.label === 'Total Boards');
        if (totalBoardsDataset) {
            maxTotalBoards = Math.max(...totalBoardsDataset.data.filter(n => typeof n === 'number'));
        }
    }

    for (const [referenceLabel, targets] of Object.entries(compareList)) {
        if (targets.includes(label)) {
            let referenceValue = null;

            if (referenceLabel === 'Max Total Boards') {
                const currentTotalBoards = chart.data.datasets.find(ds => ds.label === 'Total Boards')?.data[index];
                if (typeof currentTotalBoards === 'number' && currentTotalBoards !== maxTotalBoards) {
                    referenceValue = maxTotalBoards;
                } else {
                    continue;
                }
            } else {
                const refDataset = chart.data.datasets.find(ds => ds.label === referenceLabel);
                if (refDataset) {
                    referenceValue = refDataset.data[index];
                }
            }

            if (typeof referenceValue === 'number' && referenceValue !== 0) {
                const percent = ((current / referenceValue) * 100).toFixed(1);
                lines.push(`vs ${referenceLabel} (${referenceValue}): ${percent}%`);
            }
        }
    }

    // 🎯 EXTRA: Add Scrap or Repaired breakdown by board_model
    const labels = chart.data.labels;
    const dayKey = labels[index]; // Format: 'YYYY-MM-DD'
    const timelineDay = window.timeline[dayKey];

    if (timelineDay && (label === 'Scrap' || label === 'Awaiting Functional Test')) {
        const totalBoardModels = {};
        const targetBoardModels = {};
        const labelTitle = label === 'Scrap' ? 'Scrap Rate by Model:' : 'Repaired Rate by Model:';
        const tagName = label === 'Scrap' ? 'Scrap' : 'Awaiting Functional Test';

        // Tally Total Boards
        if (timelineDay['Total Boards']) {
            for (const hb of timelineDay['Total Boards']) {
                const model = hb.board_model || 'Unknown';
                totalBoardModels[model] = (totalBoardModels[model] || 0) + 1;
            }
        }

        // Tally label-specific (Scrap or Awaiting Functional Test)
        if (timelineDay[tagName]) {
            for (const hb of timelineDay[tagName]) {
                const model = hb.board_model || 'Unknown';
                targetBoardModels[model] = (targetBoardModels[model] || 0) + 1;
            }
        }

        lines.push('');
        lines.push(labelTitle);

        for (const model in totalBoardModels) {
            const total = totalBoardModels[model];
            const count = targetBoardModels[model] || 0;
            const rate = ((count / total) * 100).toFixed(1);
            lines.push(`${model} (${count}/${total}): ${rate}%`);
        }
    }

    return lines;
}






function toolTipCallBack_OLD(context) {
    const dataset = context.dataset;
    const index = context.dataIndex;
    const label = dataset.label || '';
    const current = context.parsed.y;

    const delta = index > 0 && typeof dataset.data[index - 1] === 'number'? current - dataset.data[index - 1] : null;
    const sign = delta!== null && delta > 0? '+' : '-';
    
    const lines = [
      `${label}: ${current}${delta!== null && delta!== 0? ` (${sign}${Math.abs(delta)})` : ''}`
    ];

    const compareList = {
        'Total Processed': ['Scrap', 'Passed Initial Diagnosis', 'Awaiting Functional Test', 'Total Good'],
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
                const currentTotalBoards = chart.data.datasets.find(ds => ds.label === 'Total Boards')?.data[index];
                // Only show 'vs Max Total Boards' if current point is different from max
                if (typeof currentTotalBoards === 'number' && currentTotalBoards !== maxTotalBoards) {
                    referenceValue = maxTotalBoards;
                } else {
                    continue; // Skip adding this line
                }
            } else {
                const refDataset = chart.data.datasets.find(ds => ds.label === referenceLabel);
                if (refDataset) {
                    referenceValue = refDataset.data[index];
                }
            }
            
            if (typeof referenceValue === 'number' && referenceValue !== 0) {
                const percent = ((current / referenceValue) * 100).toFixed(1);
                lines.push(`vs ${referenceLabel} (${referenceValue}): ${percent}%`);
            }
        }
    }

    return lines;
}


async function renderChart(data){

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

    // Get weekend boxes (now async)
    const weekendAnnotations = await generateWeekendBoxes(data.labels);

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
                    display: false
                },
                legend: {
                    display: true,
                    position: 'top'
                },
                annotation: {
                    display: true,
                    annotations: weekendAnnotations
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
        const issues = dayData[label];
        if (Array.isArray(issues) && issues.some(issue => issue.serial === serial)) {
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
    const issues = {};
    const timelineKeys = Object.keys(window.timeline);
    const currentIndex = timelineKeys.indexOf(dateStr);
    
    for (let offset = -1; offset < 2; offset++) {
        const targetIndex = currentIndex + offset;
        if (targetIndex >= 0 && targetIndex < timelineKeys.length) {
            const targetDate = timelineKeys[targetIndex];
            issues[offset] = window.timeline[targetDate]?.[label] || [];
        } else {
            issues[offset] = [];
        }
    }

    function initial(str) {
        if (!str || typeof str !== 'string') return '?';
        return str.trim().split(/\s+/).map(word => word[0]?.toUpperCase() || '').join('');
    }
    

    function annotateIssues(baseList, offsetDirection, descriptor) {
        return baseList.map(issue => {
            const relatedLabel = findSerialLabel(changeDay(dateStr, offsetDirection), issue.serial);
            return { serial: issue.serial, display: `(${initial(issue.assignee)}) ${issue.serial} - ${descriptor} ${relatedLabel}` };
        });
    }

    const removed_issues = annotateIssues(
        issues[-1].filter(
            oldIssue => !issues[0].some(current => current.serial === oldIssue.serial)
        ),
        0,
        'to'
    ).sort((a, b) => a.display.localeCompare(b.display));;

    const unchanged_issues = issues[0]
        .filter(current => issues[-1].some(old => old.serial === current.serial))
        .map(issue => ({ serial: issue.serial, display: `(${initial(issue.assignee)}) ${issue.serial}` }))
        .sort((a, b) => a.display.localeCompare(b.display));

    const added_issues = annotateIssues(
        issues[0].filter(
            current => !issues[-1].some(old => old.serial === current.serial)
        ),
        -1,
        'from'
    ).sort((a, b) => a.display.localeCompare(b.display));;

    const diffConfig = [
        { title: 'Removed Serials', color: 'red', data: removed_issues },
        { title: 'Unchanged Serials', color: 'black', data: unchanged_issues },
        { title: 'Added Serials', color: 'green', data: added_issues },
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

// Update button functionality
document.getElementById('update-button').addEventListener('click', async () => {
    const rtNumber = currentOrderKey;
    const progressBar = document.getElementById('progressBar');
    const progressLabel = document.getElementById('progressLabel');

    if (!rtNumber) {
        alert('No order loaded. Please provide a key parameter in the URL.');
        return;
    }

    textArea = document.getElementById('response');
    textArea.value = '';

    const response = await fetch('/api/update_issues', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ rt_number: rtNumber })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let maxIssues = 0;

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let lines = buffer.split('\n');
        buffer = lines.pop(); // Keep the last partial line (if any)

        for (const line of lines) {
            if (line.trim() === '') continue;
            try {
                const json = JSON.parse(line);
            
                if ('progress_update' in json) {
                    progressBar.style.display = 'block'; // Show the bar
                    progressLabel.style.display = 'block'; //show the progress label
                    maxIssues = json.total;
                    progressBar.max = json.total;
                    progressBar.value = json.current;
                    progressLabel.textContent = `${json.current}/${json.total}`;
                } else {
                    log(line);
                }
            } catch (err) {
                log(`Error: ${err}`);
            }
            
        }
    }

    // Handle final leftover
    if (buffer.trim()) {
        const json = JSON.parse(buffer);
        const stringified = createHbString(json);
        log(stringified);
    }

    progressBar.value = maxIssues;
    progressBar.style.display = 'none';
    progressLabel.style.display = 'none';
    
    // Reload the timeline data to refresh the chart with updated information
    if (currentOrderKey) {
        await loadTimelineData(currentOrderKey);
    }
    
});

function log(data){
    textArea = document.getElementById('response');
    textArea.display = 'block';
    textArea.value += data + '\n';

    setTimeout(() => {
        textArea.style.display = 'none';
    }, 5000);
}