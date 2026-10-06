// Filters the projects table by search text and status.
// Everything happens in the browser; no server request is needed.

const searchBox = document.getElementById("project-search");
const statusFilter = document.getElementById("status-filter");
const rows = document.querySelectorAll("#projects-table tr.project-row");
const noResults = document.getElementById("no-results");

function filterProjects() {
    const text = searchBox.value.toLowerCase();
    const status = statusFilter.value;
    let visibleCount = 0;

    rows.forEach(function (row) {
        const project = row.cells[0].textContent.toLowerCase();
        const client = row.cells[1].textContent.toLowerCase();

        const matchesText = project.includes(text) || client.includes(text);
        const matchesStatus = status === "All" || row.dataset.status === status;

        if (matchesText && matchesStatus) {
            row.style.display = "";
            visibleCount++;
        } else {
            row.style.display = "none";
        }
    });

    // Show the "no results" row only when nothing matched
    noResults.style.display = visibleCount === 0 ? "" : "none";
}

searchBox.addEventListener("input", filterProjects);
statusFilter.addEventListener("change", filterProjects);