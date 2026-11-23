/* Search, filters, and sorting for the employee directory tables. */
document.querySelectorAll('[data-directory]').forEach((directory) => {
    const body = directory.querySelector('tbody');
    const empty = body.querySelector('[data-directory-empty]');
    const rows = Array.from(body.rows).filter((row) => row !== empty);
    const search = directory.querySelector('[data-directory-search]');
    const filters = Array.from(directory.querySelectorAll('[data-filter-column]'));
    const sort = directory.querySelector('[data-directory-sort]');
    const cellText = (row, column) => row.cells[column].textContent.trim();

    filters.forEach((filter) => {
        const values = [...new Set(rows.map((row) => cellText(row, Number(filter.dataset.filterColumn))))];
        values.sort((a, b) => a.localeCompare(b)).forEach((value) => {
            filter.add(new Option(value, value));
        });
    });

    const summary = directory.querySelector('[data-directory-summary]');
    const statuses = directory.dataset.directory === 'documents' ? ['Uploaded', 'Sample'] : ['Active', 'Inactive'];
    [['Total records', rows.length], ...statuses.map((status) => [status, rows.filter((row) => cellText(row, 4) === status).length])].forEach(([label, count]) => {
        const card = document.createElement('div');
        card.className = 'card summary';
        const title = document.createElement('p');
        title.className = 'summary-label';
        title.textContent = label;
        const value = document.createElement('p');
        value.className = 'summary-value';
        value.textContent = count;
        card.append(title, value);
        summary.append(card);
    });

    function update() {
        const query = search.value.trim().toLocaleLowerCase();
        let visible = 0;
        rows.forEach((row) => {
            row.hidden = !row.textContent.toLocaleLowerCase().includes(query) || filters.some((filter) => (
                filter.value && cellText(row, Number(filter.dataset.filterColumn)) !== filter.value
            ));
            if (!row.hidden) visible++;
        });
        const [field, direction] = sort.value.split('-');
        [...rows].sort((a, b) => {
            const comparison = field === 'date'
                ? Date.parse(cellText(a, 3)) - Date.parse(cellText(b, 3))
                : cellText(a, 0).localeCompare(cellText(b, 0));
            return direction === 'desc' ? -comparison : comparison;
        }).forEach((row) => body.insertBefore(row, empty));
        empty.hidden = visible !== 0;
        directory.querySelector('[data-directory-count]').textContent = `Showing ${visible} of ${rows.length} ${directory.dataset.directory}`;
    }

    search.addEventListener('input', update);
    filters.forEach((filter) => filter.addEventListener('change', update));
    sort.addEventListener('change', update);
    directory.querySelector('[data-directory-clear]').addEventListener('click', () => {
        search.value = '';
        filters.forEach((filter) => { filter.value = ''; });
        sort.value = 'name-asc';
        update();
        search.focus();
    });
    update();
});
