const form = document.getElementById('rt-form');
const responseTextArea = document.getElementById('response');
const rtSelect = document.getElementById('rt_number');
let maxIssues = 0;

function createHbString(hashboard) {
    if ('progress_update' in hashboard) {
        return `\nTotal Issues: ${hashboard.total}, Proccessing at: ${hashboard.current}\n`;
    }

    const initials = (author) =>
        author.split(/\s+/).map(word => word[0].toUpperCase()).join('');

    let answer = `\n${hashboard.serial} (${hashboard.board_model})\n${hashboard.repair_summary}\n`;

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

// Fetch orders and populate dropdown
async function loadOrders() {
    try {
        const response = await fetch('/get_orders');
        const orders = await response.json();
        rtSelect.innerHTML = '';  // Clear current options

        orders.forEach(order => {
            const option = document.createElement('option');
            option.value = order.rt_num;  // only RT number is sent on submit
            option.textContent = `${order.rt_num} - ${order.summary}`;
            rtSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load orders:', error);
        rtSelect.innerHTML = '<option value="">Failed to load</option>';
    }
}

loadOrders(); // load when page loads

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const rtNumber = rtSelect.value;
    responseTextArea.value = '';  // Clear previous results

    const response = await fetch('/get_repair_times', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ rt_number: rtNumber })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

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
                    const progressBar = document.getElementById('progressBar');
                    const progressLabel = document.getElementById('progressLabel');
                    progressBar.style.display = 'block'; // Show the bar
                    progressLabel.style.display = 'block'; //show the progress label
                    maxIssues = json.total;
                    progressBar.max = json.total;
                    progressBar.value = json.current;
                    progressLabel.textContent = `${json.current}/${json.total}`;
                } else {
                    const stringified = createHbString(json);
                    responseTextArea.value += stringified;
                    responseTextArea.scrollTop = responseTextArea.scrollHeight;
                }
            } catch (err) {
                console.error("Failed to parse JSON:", line, err);
            }
            
        }
    }

    // Handle final leftover
    if (buffer.trim()) {
        const json = JSON.parse(buffer);
        const stringified = createHbString(json);
        responseTextArea.value += stringified;
        responseTextArea.scrollTop = responseTextArea.scrollHeight;
    }

    progressBar.value = maxIssues;
    progressBar.style.display = 'none';
    progressLabel.style.display = 'none';

});