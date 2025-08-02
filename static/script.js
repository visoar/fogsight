document.addEventListener('DOMContentLoaded', () => {
    // -----------------------------------------------------------------------
    // 1. CONFIGURATION & TRANSLATIONS
    // -----------------------------------------------------------------------
    const config = { apiBaseUrl: '', defaultLang: 'zh' };

    const translations = {
        heroTitle: { zh: "在此赋予概念以生命，转瞬之间", en: "Bring Concepts to Life Here" },
        startCreatingTitle: { zh: "开始创作", en: "Start Creating" },
        githubrepo: { zh: "Github 开源仓库", en: "Fogsight Github Repo" },
        officialWebsite: { zh: "通向 AGI 之路社区", en: "WaytoAGI Open Source Community" },
        groupChat: { zh: "联系我们/加入交流群", en: "Contact Us" },
        placeholders: {
            zh: ["微积分的几何原理", "冒泡排序","热寂", "黑洞是如何形成的"],
            en: ["What is Heat Death?", "How are black holes formed?", "What is Bubble Sort?"]
        },
        newChat: { zh: "新对话", en: "New Chat" },
        newChatTitle: { zh: "新对话", en: "New Chat" },
        chatPlaceholder: { zh: "AI 生成结果具有随机性，您可在此输入修改意见", en: "Results are random. Enter your modifications here for adjustments." },
        sendTitle: { zh: "发送", en: "Send" },
        generatingOutline: { zh: "正在生成大纲，请稍候...", en: "Generating outline, please wait..." },
        agentThinking: { zh: "Fogsight Agent 正在进行思考与规划，请稍后...", en: "Fogsight Agent is thinking and planning, please wait..." },
        generatingCode: { zh: "生成代码中...", en: "Generating code..." },
        codeComplete: { zh: "代码已完成", en: "Code generated" },
        openInNewWindow: { zh: "新窗口打开", en: "Open in new window" },
        saveAsHTML: { zh: "保存为 HTML", en: "Save as HTML" },
        shareAnimation: { zh: "分享", en: "Share"},
        linkCopied: { zh: "链接已复制", en: "Link Copied"},
        outlineTitle: { zh: "动画大纲确认", en: "Confirm Animation Outline" },
        regenerateOutline: { zh: "重新生成大纲", en: "Regenerate Outline" },
        createFromOutline: { zh: "就按这个生成动画", en: "Create from this Outline" },
        errorMessage: { zh: "抱歉，服务出现了一点问题。请稍后重试。", en: "Sorry, something went wrong. Please try again later." },
        errorLLMParseError: {zh: "返回的动画代码解析失败，请调整提示词重新生成。", en: "Failed to parse the returned animation code. Please adjust your prompt and try again."},
    };

    // -----------------------------------------------------------------------
    // 2. DOM ELEMENT & TEMPLATE REFERENCES
    // -----------------------------------------------------------------------
    const body = document.body;
    const initialForm = document.getElementById('initial-form');
    const initialInput = document.getElementById('initial-input');
    const chatForm = document.getElementById('chat-form');
    const chatLog = document.getElementById('chat-log');
    const newChatButton = document.getElementById('new-chat-button');
    const languageSwitcher = document.getElementById('language-switcher');
    
    const templates = {
        user: document.getElementById('user-message-template'),
        status: document.getElementById('agent-status-template'),
        code: document.getElementById('agent-code-template'),
        player: document.getElementById('animation-player-template'),
        error: document.getElementById('agent-error-template'),
        outline: document.getElementById('agent-outline-template'),
    };

    // -----------------------------------------------------------------------
    // 3. STATE MANAGEMENT
    // -----------------------------------------------------------------------
    let currentLang = config.defaultLang;
    let currentTopic = '';
    let currentOutline = '';
    let conversationHistory = [];

    // -----------------------------------------------------------------------
    // 4. CORE LOGIC (Two-Stage Generation)
    // -----------------------------------------------------------------------

    function handleInitialFormSubmit(e) {
        console.log("[Fogsight] Initial form submitted.");
        e.preventDefault();
        const topic = initialInput.value.trim();
        if (!topic) return;

        currentTopic = topic;
        const submitButton = initialForm.querySelector('button');
        submitButton.disabled = true;

        switchToChatView();
        appendUserMessage(topic);
        
        generateOutline().finally(() => {
            console.log("[Fogsight] Initial process finished, re-enabling button.");
            submitButton.disabled = false;
        });

        initialInput.value = '';
    }
    
    async function generateOutline() {
        console.log(`[Fogsight] generateOutline: Starting for topic "${currentTopic}".`);
        const agentStatusMsg = appendAgentStatus(translations.generatingOutline[currentLang]);
        
        let fullOutlineText = '';
        let outlineCardElement = null;

        try {
            const requestBody = { topic: currentTopic };
            console.log("[Fogsight] generateOutline: Making fetch request to /generate-outline with body:", JSON.stringify(requestBody));
            
            const response = await fetch(`${config.apiBaseUrl}/generate-outline`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    if(outlineCardElement) {
                        const regenerateBtn = outlineCardElement.querySelector('.regenerate-outline-button');
                        const createBtn = outlineCardElement.querySelector('.create-animation-button');
                        [regenerateBtn, createBtn].forEach(btn => btn.disabled = false);

                        regenerateBtn.addEventListener('click', () => {
                            outlineCardElement.remove();
                            generateOutline();
                        });
                        createBtn.addEventListener('click', () => {
                            [regenerateBtn, createBtn].forEach(btn => btn.disabled = true);
                            startAnimationGeneration();
                        });
                    }
                    break;
                }

                const chunk = decoder.decode(value, { stream: true });
                console.log("[Fogsight] generateOutline Stream Chunk:", chunk);
                
                const lines = chunk.split('\n\n');
                
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    
                    const jsonStr = line.substring(6);
                    if (jsonStr.trim() === '') continue;
                    
                    try {
                        const data = JSON.parse(jsonStr);
                        if (data.error) {
                            throw new Error(data.error);
                        }
                        if (data.token) {
                            if (!outlineCardElement) {
                                console.log("[Fogsight] generateOutline: First token received, creating outline card.");
                                agentStatusMsg.remove();
                                outlineCardElement = appendFromTemplate(templates.outline);
                                outlineCardElement.querySelectorAll('button').forEach(btn => btn.disabled = true);
                            }
                            fullOutlineText += data.token;
                            const outlineDisplay = outlineCardElement.querySelector('.outline-display');
                            outlineDisplay.innerHTML = marked.parse(fullOutlineText);
                        }
                    } catch (err) {
                        console.error("[Fogsight] generateOutline: Failed to parse stream JSON:", jsonStr, err);
                        if (jsonStr.includes("error")) {
                            throw new Error(`Received error from server: ${jsonStr}`);
                        }
                    }
                }
            }
            currentOutline = fullOutlineText;
            console.log("[Fogsight] generateOutline: Stream finished. Final outline set.");

        } catch (error) {
            console.error("[Fogsight] generateOutline: An error occurred in the main try-catch block:", error);
            if (agentStatusMsg) agentStatusMsg.remove();
            if (outlineCardElement) outlineCardElement.remove();
            appendErrorMessage(error.message || translations.errorMessage[currentLang]);
        }
    }

    async function startAnimationGeneration() {
        console.log("[Fogsight] startAnimationGeneration: Starting with confirmed outline.");
        const agentThinkingMessage = appendAgentStatus(translations.agentThinking[currentLang]);
        
        let fullResponseText = '';
        let codeBlockElement = null;

        try {
            const requestBody = { topic: currentTopic, outline: currentOutline, history: conversationHistory };
            console.log("[Fogsight] startAnimationGeneration: Making fetch request to /generate-animation with body:", JSON.stringify(requestBody, null, 2));

            const response = await fetch(`${config.apiBaseUrl}/generate-animation`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n\n');

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    
                    const jsonStr = line.substring(6);
                    if (jsonStr.trim() === '') continue;

                    let data;
                    try { data = JSON.parse(jsonStr); } catch (e) { continue; }
                    
                    if (data.event === 'done') {
                        console.log("[Fogsight] startAnimationGeneration: 'done' event received. Animation ID:", data.animation_id);
                        if (agentThinkingMessage) agentThinkingMessage.remove();
                        if (codeBlockElement) codeBlockElement.remove();
                        conversationHistory.push({ role: 'assistant', content: fullResponseText });

                        const match = fullResponseText.match(/<final_output>([\s\S]*?)<\/final_output>/);
                        if (match && match[1]) {
                            appendAnimationPlayer(match[1].trim(), data.animation_id);
                        } else {
                            throw new Error(translations.errorLLMParseError[currentLang]);
                        }
                        scrollToBottom();
                        return;
                    }

                    if (data.event === 'error') throw new Error(data.message);
                    
                    // **FIX**: Moved the logic inside the `if (data.token)` block
                    if (data.token) {
                        const token = data.token; // Define token here
                        if (!codeBlockElement) {
                            if (agentThinkingMessage) agentThinkingMessage.remove();
                            codeBlockElement = appendCodeBlock();
                        }
                        fullResponseText += token;
                        updateCodeBlock(codeBlockElement, token);
                    }
                }
            }
        } catch (error) {
            console.error("[Fogsight] startAnimationGeneration: An error occurred:", error);
            if (agentThinkingMessage) agentThinkingMessage.remove();
            if (codeBlockElement) codeBlockElement.remove();
            appendErrorMessage(error.message || translations.errorMessage[currentLang]);
        }
    }
    
    // -----------------------------------------------------------------------
    // 5. UI & TEMPLATE HELPERS
    // -----------------------------------------------------------------------
    function switchToChatView() {
        body.classList.remove('show-initial-view');
        body.classList.add('show-chat-view');
        languageSwitcher.style.display = 'none';
        document.getElementById('logo-chat').style.display = 'block';
    }

    function appendFromTemplate(template, text) {
        const node = template.content.cloneNode(true);
        const element = node.firstElementChild;
        if (text) {
            const p = element.querySelector('p');
            if (p) p.textContent = text;
            else element.innerHTML = element.innerHTML.replace('${text}', text);
        }
        element.querySelectorAll('[data-translate-key]').forEach(el => {
            const key = el.dataset.translateKey;
            const translation = translations[key]?.[currentLang];
            if (translation) el.textContent = translation;
        });
        chatLog.appendChild(element);
        scrollToBottom();
        return element;
    }

    const appendUserMessage = (text) => appendFromTemplate(templates.user, text);
    const appendAgentStatus = (text) => appendFromTemplate(templates.status, text);
    const appendErrorMessage = (text) => appendFromTemplate(templates.error, text);
    const appendCodeBlock = () => appendFromTemplate(templates.code);

    function updateCodeBlock(codeBlockElement, text) {
        const codeElement = codeBlockElement.querySelector('code');
        if (!text || !codeElement) return;
        const span = document.createElement('span');
        span.textContent = text;
        codeElement.appendChild(span);
        const codeContent = codeElement.closest('.code-content');
        if (codeContent) {
            requestAnimationFrame(() => codeContent.scrollTop = codeContent.scrollHeight);
        }
    }

    function appendAnimationPlayer(htmlContent, animationId) {
        const node = templates.player.content.cloneNode(true);
        const playerElement = node.firstElementChild;
        
        playerElement.querySelectorAll('[data-translate-key]').forEach(el => {
            el.textContent = translations[el.dataset.translateKey]?.[currentLang] || el.textContent;
        });
        
        const iframe = playerElement.querySelector('.animation-iframe');
        iframe.srcdoc = htmlContent;

        const shareButton = playerElement.querySelector('.share-animation');
        shareButton.addEventListener('click', () => {
            const shareUrl = `${window.location.origin}/view/${animationId}`;
            navigator.clipboard.writeText(shareUrl).then(() => {
                const span = shareButton.querySelector('span');
                const originalText = span.textContent;
                span.textContent = translations.linkCopied[currentLang];
                setTimeout(() => { span.textContent = originalText; }, 2000);
            }).catch(err => console.error('Failed to copy link:', err));
        });

        playerElement.querySelector('.open-new-window').addEventListener('click', () => {
            const blob = new Blob([htmlContent], { type: 'text/html' });
            window.open(URL.createObjectURL(blob), '_blank');
        });
        
        playerElement.querySelector('.save-html').addEventListener('click', () => {
            const blob = new Blob([htmlContent], { type: 'text/html' });
            const a = Object.assign(document.createElement('a'), { 
                href: URL.createObjectURL(blob), 
                download: `${currentTopic.replace(/\s/g, '_') || 'animation'}.html` 
            });
            a.click();
            URL.revokeObjectURL(a.href);
            a.remove();
        });

        chatLog.appendChild(playerElement);
        scrollToBottom();
    }
    
    const scrollToBottom = () => chatLog.scrollTo({ top: chatLog.scrollHeight, behavior: 'smooth' });

    // -----------------------------------------------------------------------
    // 6. INITIALIZATION
    // -----------------------------------------------------------------------
    function init() {
        initialForm.addEventListener('submit', handleInitialFormSubmit);
        
        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            alert("多轮对话微调功能正在开发中。请点击“新对话”开始新的创作。");
        });
        
        newChatButton.addEventListener('click', () => location.reload());

        languageSwitcher.addEventListener('click', (e) => {
            const target = e.target.closest('button');
            if (target) setLanguage(target.dataset.lang);
        });

        const savedLang = localStorage.getItem('preferredLanguage') || (navigator.language?.startsWith('zh') ? 'zh' : 'en');
        setLanguage(savedLang);
    }
    
    function setLanguage(lang) {
        if (!['zh', 'en'].includes(lang)) return;
        currentLang = lang;
        document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
        document.querySelectorAll('[data-translate-key]').forEach(el => {
            const key = el.dataset.translateKey;
            const translation = translations[key]?.[lang];
            if (translation) {
                if (el.hasAttribute('placeholder')) el.placeholder = translation;
                else if (el.hasAttribute('title')) el.title = translation;
                else el.textContent = translation;
            }
        });
        languageSwitcher.querySelectorAll('button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.lang === lang);
        });
        localStorage.setItem('preferredLanguage', lang);
    }

    init();
});