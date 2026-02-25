/**
 * Search highlight functions for HTML viewers.
 *
 * Called from Python via WebView.RunScript(). Three functions provide the
 * full search-highlight lifecycle:
 *
 *   shlMark(query)  — find all matches in .content, wrap in <mark> elements
 *   shlFocus(idx)   — move the "current match" cursor to match N
 *   shlClear()      — remove all highlights, restore original DOM
 *
 * DOM contract:
 *   - All operations target the first element with class "content".
 *   - Highlighted spans are <mark class="_shl"> (blue background).
 *   - The currently focused match also gets class "_cur" (filled blue).
 *   - A <style id="_shl-css"> block is injected once on first use.
 *
 * Highlight algorithm (shlMark):
 *   1. Remove any existing <mark._shl> elements (unwrap children).
 *   2. Normalize the DOM to merge adjacent text nodes.
 *   3. Walk all text nodes inside .content via TreeWalker.
 *   4. Collect {node, offset} for every case-insensitive match.
 *   5. Wrap matches in reverse DOM order so earlier offsets stay valid
 *      (wrapping splits text nodes, which would invalidate later offsets
 *      if we processed front-to-back).
 *   6. Return total match count (Python reads this to update the UI label).
 */

/**
 * Highlight all occurrences of `query` inside the .content element.
 *
 * Injects a <style> block on first call for highlight colors. Clears any
 * previous highlights before searching. Case-insensitive.
 *
 * @param {string} query - The search string to highlight.
 * @returns {number} Total number of matches found (0 if query is empty).
 */
// noinspection JSUnusedGlobalSymbols — called from Python via WebView.RunScript()
function shlMark(query) {
    /* Inject highlight CSS once ----------------------------------------- */
    if (!document.getElementById('_shl-css')) {
        const s = document.createElement('style');
        s.id = '_shl-css';
        s.textContent = 'mark._shl{background:#CCDEFF;border-radius:2px;padding:0 1px}'
            + 'mark._shl._cur{background:#007AFF;color:#fff;border-radius:2px;padding:0 1px}'
            + '@media(prefers-color-scheme:dark){'
            + 'mark._shl{background:#1a3a5c}'
            + 'mark._shl._cur{background:#4a9eff}'
            + '}';
        document.head.appendChild(s);
    }

    const content = document.querySelector('.content');
    if (!content) return 0;

    /* Clear previous highlights ----------------------------------------- */
    let marks = content.querySelectorAll('mark._shl');
    for (let j = 0; j < marks.length; j++) {
        const m = marks[j], p = m.parentNode;
        while (m.firstChild) p.insertBefore(m.firstChild, m);
        p.removeChild(m);
    }
    content.normalize();   /* merge adjacent text nodes after unwrap */

    if (!query) return 0;

    /* Walk all text nodes and collect match positions -------------------- */
    const lq = query.toLowerCase();
    const qLen = query.length;
    const walker = document.createTreeWalker(
        content, NodeFilter.SHOW_TEXT, null);
    const allMatches = [];
    while (walker.nextNode()) {
        const node = walker.currentNode;
        const lt = node.textContent.toLowerCase();
        let idx = 0;
        while ((idx = lt.indexOf(lq, idx)) !== -1) {
            allMatches.push({node: node, offset: idx});
            idx += qLen;
        }
    }

    /* Wrap matches in reverse order to preserve text-node offsets -------- */
    for (let i = allMatches.length - 1; i >= 0; i--) {
        const match = allMatches[i];
        const range = document.createRange();
        range.setStart(match.node, match.offset);
        range.setEnd(match.node, match.offset + qLen);
        const mark = document.createElement('mark');
        mark.className = '_shl';
        range.surroundContents(mark);
    }

    return allMatches.length;
}

/**
 * Move the "current match" cursor to the match at `idx`.
 *
 * Removes the `_cur` class from the previously focused match (if any),
 * applies it to the new one, and scrolls it into view. Does not modify
 * the DOM structure — only toggles CSS classes.
 *
 * @param {number} idx - 0-based index into the list of <mark._shl> elements.
 */
// noinspection JSUnusedGlobalSymbols — called from Python via WebView.RunScript()
function shlFocus(idx) {
    const marks = document.querySelectorAll('mark._shl');
    if (!marks.length) return;
    const old = document.querySelector('mark._shl._cur');
    if (old) old.className = '_shl';
    if (idx >= 0 && idx < marks.length) {
        marks[idx].className = '_shl _cur';
        marks[idx].scrollIntoView({block: 'center'});
    }
}

/**
 * Remove all search highlights and restore the original DOM.
 *
 * Unwraps every <mark._shl> element (moves children back to the parent),
 * then normalizes the DOM to merge the resulting adjacent text nodes.
 */
// noinspection JSUnusedGlobalSymbols — called from Python via WebView.RunScript()
function shlClear() {
    const content = document.querySelector('.content');
    if (!content) return;
    const marks = content.querySelectorAll('mark._shl');
    for (let j = 0; j < marks.length; j++) {
        const m = marks[j], p = m.parentNode;
        while (m.firstChild) p.insertBefore(m.firstChild, m);
        p.removeChild(m);
    }
    content.normalize();
}
