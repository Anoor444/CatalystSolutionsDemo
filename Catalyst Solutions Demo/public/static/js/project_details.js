// Switches between the tabs on the project details page.
// The open tab is kept in the address (?tab=photos), so reloading the page, or coming back
// after a delete or an approval, shows the same tab. Links with data-tab-link="name" switch tabs too.

const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".tab-panel");

function showTab(name, updateAddress) {
    const panel = document.getElementById("tab-" + name);
    if (!panel) return;
    tabs.forEach(function (t) {
        const on = t.dataset.tab === name;
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
    });
    panels.forEach(function (p) { p.classList.toggle("active", p === panel); });

    if (updateAddress) {
        const url = new URL(window.location.href);
        if (name === "overview") url.searchParams.delete("tab"); else url.searchParams.set("tab", name);
        history.replaceState(null, "", url);
    }
}

tabs.forEach(function (tab, index) {
    tab.addEventListener("click", function () { showTab(tab.dataset.tab, true); });
    // Left/right arrow keys move between tabs (standard tab keyboard behavior)
    tab.addEventListener("keydown", function (event) {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
        const next = tabs[(index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        next.focus();
        showTab(next.dataset.tab, true);
    });
});

document.querySelectorAll("[data-tab-link]").forEach(function (link) {
    link.addEventListener("click", function (event) {
        event.preventDefault();
        showTab(link.dataset.tabLink, true);
        window.scrollTo({ top: document.querySelector(".tabs").offsetTop - 16, behavior: "smooth" });
    });
});

const active = document.querySelector(".tab.active");
tabs.forEach(function (t) { t.tabIndex = t === active ? 0 : -1; });
