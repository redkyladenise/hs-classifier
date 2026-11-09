document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("descriptionInput");
    const charCount = document.getElementById("charCount");
    const classifyBtn = document.getElementById("classifyBtn");
    const clearBtn = document.getElementById("clearBtn");
    const resultContainer = document.getElementById("resultContainer");

    // SVGs (Sleek, Professional, No Emojis)
    const iconHigh = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425a.247.247 0 0 1 .02-.022Z"/></svg>';
    const iconMed = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm.93-9.412-1 4.705c-.07.34.029.533.304.533.194 0 .487-.07.686-.246l-.088.416c-.287.346-.92.598-1.465.598-.703 0-1.002-.422-.808-1.319l.738-3.468c.064-.293.006-.399-.287-.47l-.451-.081.082-.381 2.29-.287zM8 5.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"/></svg>';
    const iconLow = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/></svg>';
    
    // New Structural Icons for the UX Layout
    const iconWarn = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M7.938 2.016A.13.13 0 0 1 8.002 2a.13.13 0 0 1 .063.016.15.15 0 0 1 .054.057l6.857 11.667c.036.06.035.124.002.183a.2.2 0 0 1-.054.06.1.1 0 0 1-.066.017H1.146a.1.1 0 0 1-.066-.017.2.2 0 0 1-.054-.06.18.18 0 0 1 .002-.183L7.884 2.073a.15.15 0 0 1 .054-.057zm1.044-.45a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767z"/><path d="M7.002 12a1 1 0 1 1 2 0 1 1 0 0 1-2 0zM7.1 5.995a.905.905 0 1 1 1.8 0l-.35 3.507a.552.552 0 0 1-1.1 0z"/></svg>';
    const iconInfo = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/><path d="m8.93 6.588-2.29.287-.082.38.45.083c.294.07.352.176.288.469l-.738 3.468c-.194.897.105 1.319.808 1.319.545 0 1.178-.252 1.465-.598l.088-.416c-.2.176-.492.246-.686.246-.275 0-.375-.193-.304-.533zM9 4.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0"/></svg>';
    
    // Banner Icons
    const bannerIconHigh = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 16 16"><path d="M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425a.247.247 0 0 1 .02-.022Z"/></svg>';
    const bannerIconLow = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 16 16"><path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/></svg>';

    // Character counter
    input.addEventListener("input", () => {
        const len = input.value.length;
        charCount.textContent = len;
        classifyBtn.disabled = len === 0 || len > 500;
    });

    // Clear
    clearBtn.addEventListener("click", () => {
        input.value = "";
        charCount.textContent = "0";
        classifyBtn.disabled = true;
        resultContainer.classList.add("d-none");
        resultContainer.innerHTML = "";
    });

    // Code Formatter
    const formatCode = (code, level) => {
        if (!code) return "--";
        if (level === 2) return code.substring(0, 2);
        if (level === 4) return code.substring(0, 4);
        if (level === 6) return code.substring(0, 4) + "." + code.substring(4, 6);
        if (level === 8) return code.substring(0, 4) + "." + code.substring(4, 6) + "." + code.substring(6, 8);
        return code;
    };

    // Dynamic Thresholds Map
    const thresholds = {
        8: { high: 75, med: 50 },
        6: { high: 80, med: 55 },
        4: { high: 85, med: 60 },
        2: { high: 90, med: 60 }
    };
    const chapterNames = {
        "39": "Plastics and articles thereof",
        "73": "Articles of iron or steel",
        "84": "Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof",
        "85": "Electrical machinery and equipment and parts thereof; sound recorders and reproducers; television image and sound recorders and reproducers, and parts and accessories of such articles",
        "87": "Vehicles other than railway or tramway rollingstock, and parts and accessories thereof"
    };

    const getChapterName = (code) => {
        const ch = formatCode(code, 2);
        return chapterNames[ch] || "Description unavailable";
    };
    // Badge Generator with Tooltips
    const getBadge = (band, level) => {
        let hoverText = "";
        let t = thresholds[level];

        if (band === "High") {
            hoverText = `<strong style="color: #123F36;">High Confidence (≥ ${t.high}%)</strong><br>The model is statistically certain.`;
            return `<span class="badge-custom badge-high has-tooltip">${iconHigh} High<span class="tooltip-bubble">${hoverText}</span></span>`;
        }
        if (band === "Medium") {
            hoverText = `<strong style="color: #D4AF37;">Medium Confidence (${t.med}% - ${t.high - 1}%)</strong><br>Manual review recommended.`;
            return `<span class="badge-custom badge-medium has-tooltip">${iconMed} Medium<span class="tooltip-bubble">${hoverText}</span></span>`;
        }
        if (band === "Low") {
            hoverText = `<strong style="color: #963F3F;">Low Confidence (< ${t.med}%)</strong><br>Manual verification highly recommended.`;
            return `<span class="badge-custom badge-low has-tooltip">${iconLow} Low<span class="tooltip-bubble">${hoverText}</span></span>`;
        }
        return "";
    };

    // Classify Action
    classifyBtn.addEventListener("click", async () => {
        const text = input.value.trim();
        if (!text) return;

        classifyBtn.disabled = true;
        classifyBtn.innerHTML = `
            <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
            Classifying...
        `;
        
        resultContainer.classList.remove("d-none");
        resultContainer.innerHTML = '<div class="text-center py-5 text-muted fw-bold">Analyzing classification models...</div>';

        try {
            const response = await fetch("/classify", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ description: text })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                resultContainer.innerHTML = `<div class="result-card state-error p-4"><div class="fw-bold text-danger">${data.error}</div></div>`;
            } else if (data.status === "out_of_scope") {
                resultContainer.innerHTML = `
                    <div class="result-card state-error p-5 text-center bg-white">
                        <h5 class="fw-bold text-uppercase mb-2" style="letter-spacing: 1px; color: #991b1b;">Out of Scope</h5>
                        <p class="mb-4 text-muted">${data.ui_flag || "This description does not belong to the supported chapters."}</p>
                        <a href="https://finder.tariffcommission.gov.ph/" target="_blank" class="btn btn-outline-danger fw-bold px-4">Verify with Official Resources</a>
                    </div>
                `;
            } else {
                const code = data.predicted_code;
                const bands = data.bands_out;
                const retrieval = data.retrieval;
                
                // Parse the Banner Message (Splits "For Human Verification: ..." into Title and Subtitle)
                const isWarning = data.verification_required;
                const cardStateClass = isWarning ? "state-warning" : "state-success";
                const bannerColor = isWarning ? "#D4AF37" : "var(--color-primary)";
                const bannerSVG = isWarning ? bannerIconLow : bannerIconHigh;
                
                let bannerTitle = "ASSESSMENT RESULT";
                let bannerSub = data.ui_flag || "";
                if (data.ui_flag && data.ui_flag.includes(":")) {
                    const parts = data.ui_flag.split(":");
                    bannerTitle = parts[0].trim();
                    bannerSub = parts.slice(1).join(":").trim();
                }

// 1. Inline Vagueness Flag (Now a readable badge with SVG)
                let vaguenessHtml = "";
                if (retrieval && retrieval.is_vague) {
                    vaguenessHtml = `
                        <span class="badge-custom badge-medium has-tooltip ms-2"
                            style="font-size: 0.65rem; padding: 0.25rem 0.5rem; vertical-align: middle; font-style: normal;">
                            ${iconWarn} Vague
                            <span class="tooltip-bubble">Uses generic words. Add details like material, function, or size to improve statistical accuracy.</span>
                        </span>
                    `;
                }
                // 2. Process Other Candidates
                let alternativesHtml = "";
                if (data.alternatives && data.alternatives.length > 0) {
                    // Added formatCode(m.code, m.code.length) to add the periods dynamically
                    const uniqueAlts = [...new Set(data.alternatives.map(m => formatCode(m.code, m.code.length)))].slice(0, 5);
                    
                    alternativesHtml = `
                        <div class="d-flex align-items-center justify-content-center text-muted small mt-4">
                            <span class="has-tooltip me-2" style="color: #6c757d;">
                                ${iconInfo}
                                <span class="tooltip-bubble">Alternative codes identified by the model based on similar historical phrasing.</span>
                            </span>
                            <span class="fw-bold me-2">Other Candidates:</span> ${uniqueAlts.join(", ")}
                        </div>
                    `;
                }
                // 3. Build Zone 2: Historical Reference Data (Light Gray Area)
                let retrievalHtml = "";
                if (retrieval && !retrieval.no_close_match && retrieval.distribution.length > 0) {
                    let distributionHtml = retrieval.distribution.map(item => `
                        <div class="distribution-row border-0 mb-1 pb-1">
                            <span class="fw-bold" style="color: var(--color-text);">${item.code}</span>
                            <span class="text-muted fw-bold small">${Math.round(item.share * 100)}%</span>
                        </div>
                    `).join("");

                    let examplesHtml = "";
                    if (retrieval.examples && retrieval.examples.length > 0) {
                        examplesHtml = retrieval.examples.map(ex => `
                            <div class="mb-2">
                                <div class="text-dark fst-italic">"${ex.text}"</div>
                                <div class="small text-muted fw-bold" style="font-size: 0.7rem;"><svg xmlns="http://www.w3.org/2000/svg" class="arrow-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"> <path d="M7 5v12h12" /> <path d="m15 13 4 4-4 4" /> </svg> ${Math.round(ex.similarity * 100)}% TEXT MATCH</div>
                            </div>
                        `).join("");
                    }

                    retrievalHtml = `
                        <div class="p-4 p-md-5" style="background-color: var(--color-surface);">
                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <h6 class="fw-bold mb-0" style="font-size: 1rem; letter-spacing: 1px; color: var(--color-primary);">Historical Reference Data</h6>
                                <span class="badge border text-muted bg-white rounded-1" style="font-size: 0.65rem; letter-spacing: 1px;">UNVERIFIED</span>
                            </div>
                            
                            <p class="small text-muted mb-4">
                                Based on <strong>${retrieval.total_declarations}</strong> past declarations.
                                ${retrieval.split_notice ? `<span class="fw-bold ms-1"">Note: Past declarations disagree on this item type. Review distribution carefully.</span>` : ''}
                            </p>
                            
                            <div class="row g-4 mt-1">
                                <div class="col-md-5 border-end-md pe-md-4">
                                    <h6 class="small fw-bold text-muted text-uppercase mb-3" style="font-size: 0.7rem; letter-spacing: 0.5px;">Code Distribution</h6>
                                    ${distributionHtml}
                                </div>
                                <div class="col-md-7 ps-md-4">
                                    <h6 class="small fw-bold text-muted text-uppercase mb-3" style="font-size: 0.7rem; letter-spacing: 0.5px;">Closest Masked Examples</h6>
                                    ${examplesHtml}
                                </div>
                            </div>
                        </div>
                    `;
                } else {
                    retrievalHtml = `
                        <div class="p-4 p-md-5 text-center text-muted" style="background-color: var(--color-surface);">
                            <p class="small mb-0">No close historical declarations found for this description.</p>
                        </div>
                    `;
                }

                // 4. Assemble the Final Two-Zone Card
                resultContainer.innerHTML = `
                    <div class="result-card bg-white ${cardStateClass}">
                        
                        <!-- PRINT-ONLY REPORT HEADER -->
                        <div class="d-none d-print-block text-center pt-2 pb-3 mb-2 border-bottom border-dark">
                            <h4 class="fw-bold mb-1" style="letter-spacing: 2px; color: #000;">HS/AHTN CLASSIFICATION REPORT</h4>
                            <p class="mb-0 fst-italic" style="font-size: 0.8rem; color: #555;">
                                Unofficial document. This is an assistive tool and does not constitute a legally binding classification.
                            </p>
                        </div>
                        
                        <!-- ZONE 1: The Verdict (White Background) -->
                        <div class="p-4 p-md-5 pb-5">
                            
                            <!-- Header Banner -->
                            <div class="d-flex align-items-start border-bottom pb-4 mb-4">
                                <div class="mt-1 me-3" style="color: ${bannerColor};">${bannerSVG}</div>
                                <div>
                                    <h6 class="fw-bold text-uppercase mb-1" style="color: ${bannerColor}; font-size: 0.85rem; letter-spacing: 1px;">${bannerTitle}</h6>
                                    <div class="text-muted fs-6">${bannerSub}</div>
                                </div>
                            </div>

                            <!-- Classified Description (Moved to top of Zone 1) -->
                            <div class="text-center mb-5">
                                <div class="text-uppercase fw-bold text-muted mb-1" style="font-size: 0.65rem; letter-spacing: 1px;">Classified Description</div>
                                <div class="fs-5 text-dark fst-italic">"${text}" ${vaguenessHtml}</div>
                            </div>

                            <!-- Primary Prediction (Static Code with Toggle Below) -->
                            <div class="text-center mb-5">
                                <div class="text-uppercase fw-bold text-muted mb-2" style="font-size: 0.65rem; letter-spacing: 1px;">Primary Suggested Code</div>
                                <div class="fs-1 fw-bold text-dark mb-2" style="letter-spacing: 1px;">${formatCode(code, 8)}</div>
                                
                                <details class="d-inline-block text-center custom-accordion mt-1">
                                    <summary class="text-muted small fw-bold" style="cursor: pointer; list-style: none; outline: none; font-size: 0.75rem;">
                                        Chapter Context <span class="accordion-arrow">▼</span>
                                    </summary>
                                    <div class="pt-2 text-muted small mt-2 text-start d-inline-block">
                                        <div class="mb-1 fw-bold text-dark">
                                            <svg xmlns="http://www.w3.org/2000/svg" class="arrow-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"> <path d="M7 5v12h12" /> <path d="m15 13 4 4-4 4" /> </svg>
                                            Chapter ${formatCode(code, 2)}: ${getChapterName(code)}</div>
                                        <div class="fst-italic opacity-75">You may use official Tariff Book or the Tariff finder to read official text descriptions for this code hierarchy.</div>
                                    </div>
                                </details>
                            </div>

                            <!-- Segmented String (Horizontal Layout) -->
                            <div class="d-flex align-items-center justify-content-center text-center flex-wrap gap-2 gap-md-0 mb-2">
                                
                                <!-- Chapter -->
                                <div class="px-2 px-md-3">
                                    <div class="text-muted small fw-bold" style="font-size:0.65rem; letter-spacing:1px;">CHAPTER</div>
                                    <div class="fw-bold text-dark fs-5 my-1">${formatCode(code, 2)}</div>
                                    ${getBadge(bands["2"], 2)}
                                </div>
                                
                                <div class="text-muted opacity-25 d-none d-md-block">━━━━</div>
                                
                                <!-- Heading -->
                                <div class="px-2 px-md-3">
                                    <div class="text-muted small fw-bold" style="font-size:0.65rem; letter-spacing:1px;">HEADING</div>
                                    <div class="fw-bold text-dark fs-5 my-1">${formatCode(code, 4)}</div>
                                    ${getBadge(bands["4"], 4)}
                                </div>
                                
                                <div class="text-muted opacity-25 d-none d-md-block">━━━━</div>
                                
                                <!-- Subheading -->
                                <div class="px-2 px-md-3">
                                    <div class="text-muted small fw-bold" style="font-size:0.65rem; letter-spacing:1px;">SUBHEADING</div>
                                    <div class="fw-bold text-dark fs-5 my-1">${formatCode(code, 6)}</div>
                                    ${getBadge(bands["6"], 6)}
                                </div>
                                
                                <div class="text-muted opacity-25 d-none d-md-block">━━━━</div>
                                
                                <!-- Tariff Line -->
                                <div class="px-2 px-md-3">
                                    <div class="text-muted small fw-bold" style="font-size:0.65rem; letter-spacing:1px;">TARIFF LINE</div>
                                    <div class="fw-bold text-dark fs-5 my-1">${formatCode(code, 8)}</div>
                                    ${getBadge(bands["8"], 8)}
                                </div>
                            </div>
                            
                            ${alternativesHtml}
                        </div>

                        <!-- ZONE 2: Context (Light Gray Background) -->
                        ${retrievalHtml}
                        
                        <!-- Actions Footer -->
                        <div class="p-3 border-top d-flex justify-content-end gap-2 bg-white">
                            <a href="https://finder.tariffcommission.gov.ph/" target="_blank" class="btn btn-sm btn-outline-secondary fw-bold px-3">Verify with Tariff Finder</a>
                            <button class="btn btn-sm btn-outline-secondary fw-bold px-4" id="printResultBtn">Print Report</button>
                        </div>
                    </div>
                `;

                // Accordion Arrow Animation Logic
                const details = resultContainer.querySelector('details.custom-accordion');
                if (details) {
                    const arrow = details.querySelector('.accordion-arrow');
                    details.addEventListener('toggle', () => {
                        arrow.textContent = details.open ? '▲' : '▼';
                    });
                }

                // Print Button Logic
                const printBtn = document.getElementById("printResultBtn");
                if (printBtn) {
                    printBtn.addEventListener("click", () => window.print());
                }
            }
             
        } catch (error) {
            resultContainer.innerHTML = `<div class="result-card state-error p-4"><div class="fw-bold text-danger">Server error. Please try again.</div></div>`;
        } finally {
            classifyBtn.disabled = false;
            classifyBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 16 16"><path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/></svg>
                Classify
            `;
        }
    });
});