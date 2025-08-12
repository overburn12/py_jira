/*
        <form id="rt-form">
            <label for="rt_number">Select RT Number:</label>
            <select id="rt_number" name="rt_number">
                <option value="">Loading...</option>
            </select>
            <input type="submit" value="Submit">
        </form>
*/

const form = document.getElementById('rt-form');
const rtSelect = document.getElementById('rt_number');

// Fetch orders and populate dropdown
async function loadOrders() {
    try {
        const response = await fetch('/api/get_orders');
        const orders = await response.json();
        rtSelect.innerHTML = '';  // Clear current options

        // Sort orders into groups
        const openOrders = orders.filter(order => order.is_closed === false);
        const closedOrders = orders.filter(order => order.is_closed === true);
        const emptyOrders = orders.filter(order => order.is_closed === null);

        // Helper function to create header option
        function createHeader(text) {
            const header = document.createElement('option');
            header.textContent = text;
            header.disabled = true;
            header.style.fontWeight = 'bold';
            header.style.backgroundColor = '#f0f0f0';
            header.style.color = '#333';
            header.value = '';
            return header;
        }

        // Helper function to create order option
        function createOrderOption(order, colorStyle) {
            const option = document.createElement('option');
            option.value = order.rt_num;
            option.textContent = ` (${order.created}) ${order.rt_num} - ${order.summary} [${order.issue_count}]`;
            option.style.color = colorStyle;
            return option;
        }

        // Add Open Orders section
        if (openOrders.length > 0) {
            rtSelect.appendChild(createHeader('--- Open Orders ---'));
            openOrders.forEach(order => {
                rtSelect.appendChild(createOrderOption(order, '#000000')); // Normal black
            });
        }

        // Add Closed Orders section
        if (closedOrders.length > 0) {
            rtSelect.appendChild(createHeader('--- Closed Orders ---'));
            closedOrders.forEach(order => {
                rtSelect.appendChild(createOrderOption(order, '#666666')); // Gray
            });
        }

        // Add Empty Orders section
        if (emptyOrders.length > 0) {
            rtSelect.appendChild(createHeader('--- Empty Orders ---'));
            emptyOrders.forEach(order => {
                rtSelect.appendChild(createOrderOption(order, '#999999')); // Light gray
            });
        }

    } catch (error) {
        console.error('Failed to load orders:', error);
        rtSelect.innerHTML = '<option value="">Failed to load</option>';
    }
}

loadOrders();

function log(data){
    textArea = document.getElementById('response');
    textArea.display = 'block';
    textArea.value += data + '\n';

    setTimeout(() => {
        textArea.style.display = 'none';
    }, 5000);
}

document.getElementById('update-button').addEventListener('click', async () => {
    const rtNumber = rtSelect.value;
    const progressBar = document.getElementById('progressBar');
    const progressLabel = document.getElementById('progressLabel');

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
    
});