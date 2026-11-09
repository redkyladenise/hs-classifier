document.addEventListener("DOMContentLoaded", () => {
    const fileInput = document.getElementById("csvFileInput");
    const progressArea = document.getElementById("batchProgressArea");
    const progressText = document.getElementById("batchProgressText");
    const progressBar = document.getElementById("batchProgressBar");
    const cancelBtn = document.getElementById("batchCancelBtn");
    const resultsArea = document.getElementById("batchResultsArea");
    const summaryStats = document.getElementById("batchSummaryStats");
    const resultsTableBody = document.querySelector("#batchResultsTable tbody");
    const clearBtn = document.getElementById("batchClearBtn");
    const downloadBtn = document.getElementById("batchDownloadBtn");

    let batchData = [];
    let isCancelled = false;

    // Helper: Parse CSV safely (handles quotes and commas)
    const parseCSV = (text) => {
        const rows = [];
        let currentRow = [];
        let currentCell = '';
        let inQuotes = false;

        for (let i = 0; i < text.length; i++) {
            const char = text[i];
            const nextChar = text[i + 1];

            if (char === '"') {
                if (inQuotes && nextChar === '"') {
                    currentCell += '"';
                    i++; // Skip next quote
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (char === ',' && !inQuotes) {
                currentRow.push(currentCell.trim());
                currentCell = '';
            } else if ((char === '\n' || char === '\r') && !inQuotes) {
                if (char === '\r' && nextChar === '\n') i++; // Skip \n
                currentRow.push(currentCell.trim());
                if (currentRow.some(c => c !== '')) rows.push(currentRow);
                currentRow = [];
                currentCell = '';
            } else {
                currentCell += char;
            }
        }
        if (currentCell !== '' || currentRow.length > 0) {
            currentRow.push(currentCell.trim());
            if (currentRow.some(c => c !== '')) rows.push(currentRow);
        }
        return rows;
    };

    // Handle File Selection
    fileInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const text = event.target.result.replace(/^\uFEFF/, ''); // Remove BOM
            const rows = parseCSV(text);
            
            if (rows.length < 2) {
                alert("CSV file is empty or missing headers.");
                return;
            }

            // Find description column (case-insensitive)
            const headers = rows[0].map(h => h.toLowerCase());
            let descIndex = headers.indexOf("description");
            
            if (descIndex === -1) {
                descIndex = 0; // Fallback to first column
            }

            // Extract descriptions (skipping header)
            const descriptions = rows.slice(1).map(r => r[descIndex] || "");
            
            if (descriptions.length > 200) {
                alert(`Maximum 200 rows allowed. Your file has ${descriptions.length}.`);
                fileInput.value = "";
                return;
            }

            // Prepare for processing
            startBatch(descriptions);
        };
        reader.readAsText(file);
    });

    const startBatch = async (descriptions) => {
        isCancelled = false;
        batchData = [];
        resultsArea.classList.add("d-none");
        progressArea.classList.remove("d-none");
        
        const total = descriptions.length;
        let processed = 0;
        progressBar.style.width = "0%";
        progressText.textContent = `0 / ${total}`;

        // Process in chunks of 5 (BATCH_CHUNK)
        const chunkSize = 5;
        for (let i = 0; i < total; i += chunkSize) {
            if (isCancelled) break;

            const chunk = descriptions.slice(i, i + chunkSize);
            
            try {
                const response = await fetch("/classify-batch", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ descriptions: chunk })
                });
                
                const data = await response.json();
                
                if (data.results) {
                    data.results.forEach((res, idx) => {
                        batchData.push({
                            row: i + idx + 1,
                            text: chunk[idx],
                            ...res
                        });
                    });
                }
            } catch (err) {
                console.error("Chunk failed", err);
                // Fill failed chunk with error status
                chunk.forEach((text, idx) => {
                    batchData.push({ row: i + idx + 1, text, status: "error", data: null });
                });
            }

            processed += chunk.length;
            const percent = Math.round((processed / total) * 100);
            progressBar.style.width = `${percent}%`;
            progressText.textContent = `${processed} / ${total}`;
        }

        // Handle cancellation
        if (isCancelled) {
            for (let i = processed; i < total; i++) {
                batchData.push({ row: i + 1, text: descriptions[i], status: "not_processed", data: null });
            }
        }

        progressArea.classList.add("d-none");
        renderBatchResults();
    };

    cancelBtn.addEventListener("click", () => {
        isCancelled = true;
    });

    const renderBatchResults = () => {
        resultsArea.classList.remove("d-none");
        
        const total = batchData.length;
        const inScopeData = batchData.filter(d => d.data && d.data.status === "success");
        const inScope = inScopeData.length;
        const errors = batchData.filter(d => d.status === "error" || d.status === "empty" || d.status === "too_long").length;
        const needVerify = inScopeData.filter(d => d.data.verification_required).length;
        const flaggedVague = inScopeData.filter(d => d.data.retrieval && d.data.retrieval.is_vague).length;

        let low2 = 0, low4 = 0, low6 = 0, low8 = 0;
        inScopeData.forEach(d => {
            if (d.data.bands_out["2"] === "Low") low2++;
            if (d.data.bands_out["4"] === "Low") low4++;
            if (d.data.bands_out["6"] === "Low") low6++;
            if (d.data.bands_out["8"] === "Low") low8++;
        });

        const getPercent = (val) => inScope === 0 ? 0 : Math.round((val / inScope) * 100);

        // Calculate health bar percentages (based on total rows)
        const pctOk = total === 0 ? 0 : Math.round(((inScope - needVerify) / total) * 100);
        const pctVerify = total === 0 ? 0 : Math.round((needVerify / total) * 100);
        const pctErr = total === 0 ? 0 : Math.round((errors / total) * 100);

        // 1. Render Clean SaaS-Style KPI Summary
        summaryStats.innerHTML = `
            <div class="row row-cols-5 g-4 mb-3 text-start">
                <div class="col">
                    <div class="text-muted fw-bold text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 1px;">Total Rows</div>
                    <div class="fs-3 text-dark">${total}</div>
                </div>
                <div class="col">
                    <div class="text-muted fw-bold text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 1px;">In Scope</div>
                    <div class="fs-3" style="color: var(--color-primary);">${inScope}</div>
                </div>
                <div class="col">
                    <div class="text-muted fw-bold text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 1px;">Verify</div>
                    <div class="fs-3 text-warning">${needVerify}</div>
                </div>
                <div class="col">
                    <div class="text-muted fw-bold text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 1px;">Vague</div>
                    <div class="fs-3" style="color: #d97706;">${flaggedVague}</div>
                </div>
                <div class="col">
                    <div class="text-muted fw-bold text-uppercase mb-1" style="font-size: 0.7rem; letter-spacing: 1px;">Errors</div>
                    <div class="fs-3" style="color: #963F3F;">${errors}</div>
                </div>
            </div>

            <div class="w-100 d-flex rounded-pill overflow-hidden mb-2" style="height: 6px; background-color: #e2e8f0;">
                <div style="width: ${pctOk}%; background-color: var(--color-primary); transition: width 1s ease;"></div>
                <div style="width: ${pctVerify}%; background-color: #D4AF37; transition: width 1s ease;"></div>
                <div style="width: ${pctErr}%; background-color: #963F3F; transition: width 1s ease;"></div>
            </div>

            <!-- Diagnostics String (Shifted to Left) -->
            <div class="d-flex justify-content-start text-muted small" style="font-size: 0.7rem;">
                <div>
                    <span class="fw-bold text-uppercase me-2" style="font-size: 0.65rem; letter-spacing: 1px;">Low Confidence Share:</span>
                    L2: ${getPercent(low2)}% <span class="mx-1 opacity-25">|</span> 
                    L4: ${getPercent(low4)}% <span class="mx-1 opacity-25">|</span> 
                    L6: ${getPercent(low6)}% <span class="mx-1 opacity-25">|</span> 
                    L8: ${getPercent(low8)}%
                </div>
            </div>
        `;

        // 2. Render Modern Air Table Rows
// 2. Render Modern Air Table Rows
        resultsTableBody.innerHTML = "";
        batchData.forEach(item => {
            const tr = document.createElement("tr");
            tr.style.borderBottom = "1px solid #f1f5f9"; // Soft horizontal dividers only
            
            // Inline SVGs
            const getDotSVG = (band) => {
                if (band === 'High') return `<svg width="8" height="8" viewBox="0 0 10 10" class="me-2"><circle cx="5" cy="5" r="5" fill="#123F36"/></svg>`;
                if (band === 'Medium') return `<svg width="8" height="8" viewBox="0 0 10 10" class="me-2"><circle cx="5" cy="5" r="5" fill="#D4AF37"/></svg>`;
                return `<svg width="8" height="8" viewBox="0 0 10 10" class="me-2"><circle cx="5" cy="5" r="5" fill="#963F3F"/></svg>`; 
            };

            const svgWarn = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="currentColor" class="me-1 mb-1" viewBox="0 0 16 16"><path d="M7.938 2.016A.13.13 0 0 1 8.002 2a.13.13 0 0 1 .063.016.15.15 0 0 1 .054.057l6.857 11.667c.036.06.035.124.002.183a.2.2 0 0 1-.054.06.1.1 0 0 1-.066.017H1.146a.1.1 0 0 1-.066-.017.2.2 0 0 1-.054-.06.18.18 0 0 1 .002-.183L7.884 2.073a.15.15 0 0 1 .054-.057zm1.044-.45a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767z"/><path d="M7.002 12a1 1 0 1 1 2 0 1 1 0 0 1-2 0zM7.1 5.995a.905.905 0 1 1 1.8 0l-.35 3.507a.552.552 0 0 1-1.1 0z"/></svg>`;
            const svgBan = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="currentColor" class="me-1 mb-1" viewBox="0 0 16 16"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/><path d="M4.646 4.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1-.708.708l-6-6a.5.5 0 0 1 0-.708z"/></svg>`;
            
            // Add this specific SVG under your svgBan definition
            const svgVagueInline = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="#d97706" class="ms-2 flex-shrink-0" viewBox="0 0 16 16" title="Vague Description"><path d="M7.938 2.016A.13.13 0 0 1 8.002 2a.13.13 0 0 1 .063.016.15.15 0 0 1 .054.057l6.857 11.667c.036.06.035.124.002.183a.2.2 0 0 1-.054.06.1.1 0 0 1-.066.017H1.146a.1.1 0 0 1-.066-.017.2.2 0 0 1-.054-.06.18.18 0 0 1 .002-.183L7.884 2.073a.15.15 0 0 1 .054-.057zm1.044-.45a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767z"/><path d="M7.002 12a1 1 0 1 1 2 0 1 1 0 0 1-2 0zM7.1 5.995a.905.905 0 1 1 1.8 0l-.35 3.507a.552.552 0 0 1-1.1 0z"/></svg>`;

            const viewBtn = `<button class="btn btn-sm btn-outline-secondary fw-bold rounded-pill px-3 py-1 view-details-btn" data-text="${item.text.replace(/"/g, '&quot;')}">View</button>`;
            
            if (item.status === "ok" && item.data && item.data.status === "success") {
                const d = item.data;
                const code = d.predicted_code;
                const b = d.bands_out;
                const isVague = d.retrieval && d.retrieval.is_vague;
                
                tr.innerHTML = `
                    <td class="align-middle text-muted ps-2">${item.row}</td>
                    <td class="align-middle" style="max-width: 220px;" title="${item.text}">
                        <div class="d-flex align-items-center text-dark">
                            <span class="text-truncate">${item.text}</span>
                            ${isVague ? svgVagueInline : ''}
                        </div>
                    </td>
                    <td class="align-middle d-flex align-items-center py-3">${getDotSVG(b["2"])} ${code.substring(0, 2)}</td>
                    <td class="align-middle">${getDotSVG(b["4"])} ${code.substring(0, 4)}</td>
                    <td class="align-middle">${getDotSVG(b["6"])} ${code.substring(0, 4)}.${code.substring(4, 6)}</td>
                    <td class="align-middle">${getDotSVG(b["8"])} ${code.substring(0, 4)}.${code.substring(4, 6)}.${code.substring(6, 8)}</td>
                    <td class="align-middle">${d.verification_required ? '<span class="text-dark">Yes</span>' : '<span class="text-muted ">No</span>'}</td>
                    <td class="align-middle pe-2">${viewBtn}</td>
                `;
            } else {
                let msg = "Processing error";
                let isWarning = true;
                
                if (item.status === "ok" && item.data && item.data.status === "out_of_scope") {
                    msg = "Out of Scope: May not belong to supported chapters.";
                    isWarning = false;
                } else if (item.status === "not_processed") {
                    msg = "Skipped (Cancelled)";
                    isWarning = false;
                } else if (item.status === "empty" || item.status === "too_long") {
                    msg = item.status === 'too_long' ? 'Exceeds 500 characters' : 'Empty description';
                }

                tr.innerHTML = `
                    <td class="align-middle text-muted ps-2">${item.row}</td>
                    <td class="text-truncate align-middle text-muted" style="max-width: 220px;" title="${item.text}">${item.text}</td>
                    <td class="align-middle text-muted small ${isWarning ? 'text-danger' : ''}" colspan="5">
                        ${isWarning ? svgWarn : svgBan} ${msg}
                    </td>
                    <td class="align-middle pe-2">${viewBtn}</td>
                `;
            }
            
            resultsTableBody.appendChild(tr);
        });

        // Attach event listeners to the new "Details" buttons
        document.querySelectorAll(".view-details-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const singleTab = document.getElementById("single-tab");
                const tab = new bootstrap.Tab(singleTab);
                tab.show();
                
                const text = e.target.getAttribute("data-text");
                const input = document.getElementById("descriptionInput");
                input.value = text;
                input.dispatchEvent(new Event("input"));
                
                document.getElementById("classifyBtn").click();
            });
        });
    };

    clearBtn.addEventListener("click", () => {
        fileInput.value = "";
        batchData = [];
        resultsArea.classList.add("d-none");
    });

    // --- DOWNLOAD CSV LOGIC ---
    downloadBtn.addEventListener("click", () => {
        if (batchData.length === 0) return;

        // 1. Define the 21 columns
        const headers = [
            "row_number", "description", "status", "scope",
            "chapter_code", "chapter_confidence",
            "heading_code", "heading_confidence",
            "subheading_code", "subheading_confidence",
            "line_code", "line_confidence",
            "deepest_confident_level", "verification_required",
            "line_candidates", "vagueness_flag",
            "retrieval_top_code_L4", "retrieval_split_notice",
            "model_version", "run_date"
        ];

        // 2. Helper to sanitize text and prevent CSV injection
        const sanitizeCell = (text) => {
            let str = String(text === null || text === undefined ? "" : text);
            // Excel Formula Injection Protection
            if (/^[=+\-@\t\r]/.test(str)) {
                str = "'" + str;
            }
            // Escape quotes
            return `"${str.replace(/"/g, '""')}"`;
        };

        // 3. Build the rows
        let csvContent = headers.join(",") + "\n";
        const today = new Date().toISOString().split('T')[0];

        batchData.forEach(item => {
            let row = [];
            
            // Map the data based on the batch table status
            row.push(item.row);
            row.push(item.text);
            
            // FIX: Correctly identify the status for the CSV
            let exportStatus = item.status;
            if (item.status === "ok" && item.data && item.data.status) {
                exportStatus = item.data.status; // will be "success" or "out_of_scope"
            }
            row.push(exportStatus);
            
            if (item.status === "ok" && item.data && item.data.status === "success") {
                const d = item.data;
                const code = d.predicted_code;
                const b = d.bands_out;
                const ret = d.retrieval || {};
                
                // Extract codes at each level
                const l2 = code.substring(0, 2);
                const l4 = code.substring(0, 4);
                const l6 = code.substring(0, 4) + "." + code.substring(4, 6);
                const l8 = code.substring(0, 4) + "." + code.substring(4, 6) + "." + code.substring(6, 8);

                row.push("in_scope");
                row.push(l2);
                row.push(b["2"]);
                row.push(l4);
                row.push(b["4"]);
                row.push(l6);
                row.push(b["6"]);
                row.push(l8);
                row.push(b["8"]);
                row.push(d.deepest_confident_level || "none");
                row.push(d.verification_required ? "yes" : "no");
                
                // Candidates
                if (d.alternatives && d.alternatives.length > 0) {
                    row.push(d.alternatives.map(a => a.code).join(";"));
                } else {
                    row.push("");
                }
                
                row.push(ret.is_vague ? "yes" : "no"); // vagueness_flag
                
                // Retrieval info
                if (ret.available === false || ret.no_close_match === true || !ret.distribution || ret.distribution.length === 0) {
                    row.push("");
                } else {
                    row.push(ret.distribution[0].code);
                }
                row.push(ret.split_notice ? "yes" : "no");
                
                row.push("v1-real");
                row.push(today);
                
            } else {
                // If it's out_of_scope, empty, or too_long, add the scope label and fill the rest with blanks
                if (exportStatus === "out_of_scope") {
                    row.push("out_of_scope");
                } else {
                    row.push(""); // scope
                }
                
                // Fill the remaining 16 columns with blanks (scope was 1, so 21 total - 4 used = 17 remaining)
                for (let i = 0; i < 16; i++) row.push("");
            }

            // Sanitize every cell and join with commas
            csvContent += row.map(sanitizeCell).join(",") + "\n";
        });

        // 4. Trigger Download
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `hs_suggestions_${today}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    });
});