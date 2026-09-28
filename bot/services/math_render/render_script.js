const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { mathjax } = require('mathjax-full/js/mathjax.js');
const { TeX } = require('mathjax-full/js/input/tex.js');
const { SVG } = require('mathjax-full/js/output/svg.js');
const { liteAdaptor } = require('mathjax-full/js/adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = require('mathjax-full/js/handlers/html.js');
const { AllPackages } = require('mathjax-full/js/input/tex/AllPackages.js');
const { Resvg } = require('@resvg/resvg-js');

// Initialize MathJax once
const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const tex = new TeX({
    packages: AllPackages,
    inlineMath: [['$', '$'], ['\\(', '\\)']],
    displayMath: [['$$', '$$'], ['\\[', '\\]']]
});
const svg = new SVG({ fontCache: 'local' });
const mathDoc = mathjax.document('', { InputJax: tex, OutputJax: svg });

/**
 * Preprocess and sanitize LaTeX string
 */
function cleanLatex(input) {
    let s = input.trim();
    // Strip leading/trailing $$ or \[ \] if present
    if (s.startsWith('$$') && s.endsWith('$$') && s.length >= 4) {
        s = s.slice(2, -2).trim();
    } else if (s.startsWith('\\[') && s.endsWith('\\]') && s.length >= 4) {
        s = s.slice(2, -2).trim();
    } else if (s.startsWith('$') && s.endsWith('$') && s.length >= 2) {
        s = s.slice(1, -1).trim();
    }
    return s;
}

/**
 * Renders LaTeX to a PNG Buffer with dark Telegram theme
 * @param {string} latexStr
 * @returns {Object} PNG buffer, width, height
 */
function renderFormulaPng(latexStr) {
    const cleaned = cleanLatex(latexStr);
    if (!cleaned) {
        throw new Error('Empty LaTeX formula');
    }

    const node = mathDoc.convert(cleaned, { display: true });
    const innerSvg = adaptor.innerHTML(node);

    // Check for MathJax parse error
    if (innerSvg.includes('data-mjx-error') || innerSvg.includes('<merror>')) {
        const errorMatch = innerSvg.match(/title="([^"]+)"/);
        const errMsg = errorMatch ? errorMatch[1] : 'MathJax LaTeX parse error';
        throw new Error(`Invalid LaTeX: ${errMsg}`);
    }

    // Parse viewBox: "minX minY width height"
    const vbMatch = innerSvg.match(/viewBox="([^"]+)"/);
    if (!vbMatch) {
        throw new Error('No viewBox in MathJax SVG output');
    }

    const [minX, minY, width, height] = vbMatch[1].trim().split(/\s+/).map(Number);
    if (isNaN(width) || isNaN(height) || width <= 0 || height <= 0) {
        throw new Error(`Invalid SVG dimensions: width=${width}, height=${height}`);
    }

    // Extract SVG inner elements (defs, g, etc.)
    const contentMatch = innerSvg.match(/<svg[^>]*>([\s\S]*?)<\/svg>/i);
    const innerContent = contentMatch ? contentMatch[1] : innerSvg;

    // Proportional padding in MathJax units (1ex ~ 440 units)
    // Horizontal padding: generous for nice card look
    const padX = Math.max(500, Math.round(width * 0.08));
    const padY = Math.max(350, Math.round(height * 0.20));

    const cardWidth = width + padX * 2;
    const cardHeight = height + padY * 2;
    const cardMinX = minX - padX;
    const cardMinY = minY - padY;

    // Corner radius
    const rx = Math.max(25, Math.min(60, Math.round(Math.min(cardWidth, cardHeight) * 0.08)));

    // Create standalone SVG with dark card background
    const cardSvg = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
        viewBox="${cardMinX} ${cardMinY} ${cardWidth} ${cardHeight}"
        width="${cardWidth}" height="${cardHeight}"
        style="color: #e6edf3;">
        <rect x="${cardMinX}" y="${cardMinY}" width="${cardWidth}" height="${cardHeight}" rx="${rx}" fill="#182533" />
        <g fill="#e6edf3" stroke="#e6edf3">
            ${innerContent}
        </g>
    </svg>`;

    // Scale 2-3x for crisp mobile display, max width 800px
    // In MathJax, 1ex ~ 440 units ~ 9px. Scale factor 0.055 gives ~2.7x standard font size.
    let pxWidth = Math.round(cardWidth * 0.055);
    if (pxWidth > 800) {
        pxWidth = 800; // Cap to 800px maximum
    } else if (pxWidth < 260) {
        pxWidth = 260; // Minimum card width so tiny formulas aren't microscopic
    }

    const resvg = new Resvg(cardSvg, {
        fitTo: { mode: 'width', value: pxWidth }
    });
    const rendered = resvg.render();
    return {
        buffer: rendered.asPng(),
        width: rendered.width,
        height: rendered.height
    };
}

// Daemon mode: processes JSON requests via stdin
function runDaemon() {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
        terminal: false
    });

    rl.on('line', (line) => {
        if (!line.trim()) return;
        try {
            const req = JSON.parse(line);
            const { id, latex, outPath } = req;
            const res = renderFormulaPng(latex);
            if (outPath) {
                const dir = path.dirname(outPath);
                if (!fs.existsSync(dir)) {
                    fs.mkdirSync(dir, { recursive: true });
                }
                fs.writeFileSync(outPath, res.buffer);
                process.stdout.write(JSON.stringify({
                    id,
                    success: true,
                    width: res.width,
                    height: res.height,
                    outPath
                }) + '\n');
            } else {
                process.stdout.write(JSON.stringify({
                    id,
                    success: true,
                    width: res.width,
                    height: res.height,
                    pngBase64: res.buffer.toString('base64')
                }) + '\n');
            }
        } catch (err) {
            try {
                const req = JSON.parse(line);
                process.stdout.write(JSON.stringify({
                    id: req.id,
                    success: false,
                    error: err.message
                }) + '\n');
            } catch (e) {
                process.stdout.write(JSON.stringify({
                    success: false,
                    error: err.message
                }) + '\n');
            }
        }
    });

    process.stdin.on('end', () => process.exit(0));
}

// CLI mode: node render_script.js --base64 <b64_latex> <output_png_path>
function runCli() {
    const args = process.argv.slice(2);
    if (args.includes('--daemon')) {
        runDaemon();
        return;
    }

    if (args[0] === '--base64' && args.length >= 3) {
        const b64 = args[1];
        const outPath = args[2];
        try {
            const latex = Buffer.from(b64, 'base64').toString('utf8');
            const res = renderFormulaPng(latex);
            const dir = path.dirname(outPath);
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
            }
            fs.writeFileSync(outPath, res.buffer);
            console.log(JSON.stringify({ success: true, width: res.width, height: res.height }));
            process.exit(0);
        } catch (err) {
            console.error(JSON.stringify({ success: false, error: err.message }));
            process.exit(1);
        }
    } else {
        console.error('Usage: node render_script.js --daemon OR --base64 <b64> <outPath>');
        process.exit(1);
    }
}

runCli();
