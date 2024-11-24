document.addEventListener('DOMContentLoaded', function() {
    const sendCommandButton = document.getElementById('send-command');
    const agentInput = document.getElementById('agent-input');
    const agentOutput = document.getElementById('agent-output');

    sendCommandButton.addEventListener('click', function() {
        const command = agentInput.value;
        sendCommandToBackend(command);
    });

    function sendCommandToBackend(command) {
        fetch('http://localhost:5000/command', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ command: command })
        })
        .then(response => response.json())
        .then(data => {
            displayAgentOutput(data.message);
        })
        .catch(error => {
            console.error('Error:', error);
        });
    }

    function displayAgentOutput(message) {
        const outputElement = document.createElement('p');
        outputElement.textContent = message;
        agentOutput.appendChild(outputElement);
    }
});
