document.addEventListener("DOMContentLoaded", () => {
    const chatForm = document.getElementById("chat-form");
    const queryInput = document.getElementById("query-input");
    const chatMessages = document.getElementById("chat-messages");
    const visPanel = document.getElementById("vis-panel");
    const visImage = document.getElementById("vis-image");
    const closeVisBtn = document.getElementById("close-vis-btn");
    
    // Suggestion Buttons
    const suggestBtns = document.querySelectorAll(".suggest-btn");
    
    // Sidebar Elements
    const metaMatches = document.getElementById("meta-matches-count");
    const metaPlayers = document.getElementById("meta-players-count");
    const metaDeliveries = document.getElementById("meta-deliveries-count");
    const metaGraph = document.getElementById("meta-graph-info");

    // Fetch and populate metadata on load
    fetchMetadata();

    // Close Visualization Panel
    closeVisBtn.addEventListener("click", () => {
        visPanel.style.display = "none";
    });

    // Handle suggestion button click
    suggestBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const query = btn.getAttribute("data-query");
            queryInput.value = query;
            queryInput.focus();
            // Automatically submit the query
            submitQuery(query);
        });
    });

    // Handle form submit
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query) return;
        
        queryInput.value = "";
        submitQuery(query);
    });

    async function fetchMetadata() {
        try {
            const res = await fetch("/data-info");
            if (!res.ok) throw new Error("Failed to load metadata");
            const data = await res.json();
            
            metaMatches.textContent = data.matches.count.toLocaleString();
            metaPlayers.textContent = data.players.count.toLocaleString();
            metaDeliveries.textContent = data.deliveries.count.toLocaleString();
            metaGraph.textContent = `${data.graph.nodes.toLocaleString()} Nodes / ${data.graph.edges.toLocaleString()} Edges`;
        } catch (err) {
            console.error("Error fetching metadata:", err);
            metaMatches.textContent = "Error";
            metaPlayers.textContent = "Error";
            metaDeliveries.textContent = "Error";
            metaGraph.textContent = "Error";
        }
    }

    async function submitQuery(query) {
        // 1. Append User Message
        appendMessage("user", query);
        
        // 2. Show Typing Indicator
        const typingIndicator = showTypingIndicator();
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            // 3. Make API request
            const res = await fetch("/query", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ query: query })
            });

            // Remove typing indicator
            typingIndicator.remove();

            if (!res.ok) {
                const errorData = await res.json();
                throw new Error(errorData.detail || "Server error occurred");
            }

            const data = await res.json();
            let responseText = data.response;

            // 4. Check if chart was created
            const chartMatch = responseText.match(/\[CHART_CREATED:(chart_\d+\.png)\]/);
            if (chartMatch) {
                const chartFilename = chartMatch[1];
                // Extract tag from response text
                responseText = responseText.replace(chartMatch[0], "");
                
                // Show visualization panel
                visImage.src = `/static/${chartFilename}`;
                visPanel.style.display = "block";
            }

            // 5. Append Agent Message
            appendMessage("agent", responseText);
            
        } catch (err) {
            if (typingIndicator) typingIndicator.remove();
            appendMessage("system", `Error: ${err.message}`);
        }
        
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function appendMessage(sender, text) {
        const messageDiv = document.createElement("div");
        messageDiv.className = `message ${sender}-message`;
        
        const contentDiv = document.createElement("div");
        contentDiv.className = "message-content";
        
        if (sender === "agent") {
            contentDiv.innerHTML = formatMarkdown(text);
        } else {
            const p = document.createElement("p");
            p.textContent = text;
            contentDiv.appendChild(p);
        }
        
        messageDiv.appendChild(contentDiv);
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function showTypingIndicator() {
        const indicatorDiv = document.createElement("div");
        indicatorDiv.className = "typing-indicator";
        
        for (let i = 0; i < 3; i++) {
            const dot = document.createElement("span");
            dot.className = "typing-dot";
            indicatorDiv.appendChild(dot);
        }
        
        chatMessages.appendChild(indicatorDiv);
        return indicatorDiv;
    }

    // A lightweight helper to format Markdown structures (bold, lists, code, tables) into HTML
    function formatMarkdown(text) {
        let html = text;

        // Escape HTML to prevent injection
        html = html
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Code blocks: ```python ... ```
        html = html.replace(/```python([\s\S]*?)```/g, (match, code) => {
            return `<pre><code class="language-python">${code.trim()}</code></pre>`;
        });
        html = html.replace(/```([\s\S]*?)```/g, (match, code) => {
            return `<pre><code>${code.trim()}</code></pre>`;
        });

        // Inline code: `code`
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

        // Headers: ### Header or ## Header
        html = html.replace(/^\s*###\s+(.+)$/gm, "<h3>$1</h3>");
        html = html.replace(/^\s*##\s+(.+)$/gm, "<h2>$1</h2>");
        html = html.replace(/^\s*#\s+(.+)$/gm, "<h1>$1</h1>");

        // Bold: **text**
        html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

        // Unordered lists: - item or * item
        html = html.replace(/^\s*[-*]\s+(.+)$/gm, "<li>$1</li>");
        // Wrap contiguous list items in <ul>
        // This is a simple regex grouping to wrap list elements
        html = html.replace(/(<li>.*<\/li>)/g, "<ul>$1</ul>");
        // Fix nested <ul> tags created by line-by-line replacement
        html = html.replace(/<\/ul>\s*<ul>/g, "");

        // Render simple tables
        // Find markdown table blocks and parse them
        const lines = html.split("\n");
        let inTable = false;
        let tableHtml = "";
        let newLines = [];

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            if (line.startsWith("|") && line.endsWith("|")) {
                const cells = line.split("|").map(c => c.trim()).filter((c, idx, arr) => idx > 0 && idx < arr.length - 1);
                
                // Skip separator rows (e.g. |---|---|)
                if (line.includes("-") && cells.every(c => c.match(/^-+$/))) {
                    continue;
                }

                if (!inTable) {
                    inTable = true;
                    tableHtml = "<table><thead><tr>";
                    cells.forEach(cell => {
                        tableHtml += `<th>${cell}</th>`;
                    });
                    tableHtml += "</tr></thead><tbody>";
                } else {
                    tableHtml += "tr><td>" + cells.join("</td><td>") + "</td></tr>";
                }
            } else {
                if (inTable) {
                    tableHtml += "</tbody></table>";
                    newLines.push(tableHtml);
                    inTable = false;
                    tableHtml = "";
                }
                newLines.push(line);
            }
        }
        if (inTable) {
            tableHtml += "</tbody></table>";
            newLines.push(tableHtml);
        }

        // Rejoin and handle single linebreaks (outside tags)
        html = newLines.join("\n");
        
        // Convert single linebreaks to <br> where appropriate
        // Simple workaround: replace \n with <br> unless it's inside block tags
        html = html.replace(/\n/g, "<br>");
        html = html.replace(/<br>(?=<\/?(ul|li|table|thead|tbody|tr|th|td|h[1-3]|pre|code))/g, "");
        html = html.replace(/(<\/(ul|table|h[1-3]|pre)>)<br>/g, "$1");

        return html;
    }
});
