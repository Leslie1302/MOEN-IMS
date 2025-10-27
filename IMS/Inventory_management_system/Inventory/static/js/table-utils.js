/**
 * EnhancedTable - A lightweight, dependency-free table enhancement library
 * Provides sorting, filtering, pagination, and export functionality
 */
class EnhancedTable {
    constructor(options) {
        this.table = typeof options.table === 'string' 
            ? document.querySelector(options.table) 
            : options.table;
            
        this.config = {
            searchable: options.searchable !== false,
            sortable: options.sortable !== false,
            pagination: options.pagination !== false,
            rowsPerPage: options.rowsPerPage || 25,
            exportable: options.exportable || false,
            exportFormats: options.exportFormats || ['csv', 'excel', 'print'],
            exportFileName: options.exportFileName || 'table_export',
            exportOptions: {
                title: options.exportOptions?.title || 'Table Export',
                orientation: options.exportOptions?.orientation || 'portrait',
                pageSize: options.exportOptions?.pageSize || 'A4',
                margin: options.exportOptions?.margin || '1cm'
            },
            columnDefs: options.columnDefs || []
        };

        this.currentPage = 1;
        this.sortColumn = null;
        this.sortDirection = 'asc';
        this.filteredData = [];
        this.originalData = [];

        this.init();
    }

    init() {
        if (!this.table) {
            console.error('EnhancedTable: Table element not found');
            return;
        }

        // Add CSS for filter inputs if not already added
        this.addFilterStyles();

        // Store original data
        this.cacheOriginalData();
        this.filteredData = [...this.originalData];

        // Initialize features
        if (this.config.searchable) this.initSearch();
        if (this.config.sortable) this.initSorting();
        if (this.config.pagination) this.initPagination();
        if (this.config.exportable) this.initExport();
        
        // Initialize column filters
        this.initColumnFilters();

        // Apply initial sort if specified
        const initialSortCol = this.table.querySelector('th[data-sort-initial]');
        if (initialSortCol) {
            const colIndex = Array.from(initialSortCol.parentElement.children).indexOf(initialSortCol);
            this.sortColumn = colIndex;
            this.sortDirection = initialSortCol.getAttribute('data-sort-initial') || 'asc';
            this.sortTable(colIndex, true);
        }

        // Initial render
        this.render();
    }

    cacheOriginalData() {
        const rows = Array.from(this.table.querySelectorAll('tbody tr'));
        this.originalData = rows.map(row => ({
            element: row,
            cells: Array.from(row.cells).map(cell => ({
                text: cell.textContent.trim(),
                sortValue: cell.getAttribute('data-sort-value') || cell.textContent.trim(),
                element: cell,
                // Store original display style to restore when filters are cleared
                originalDisplay: cell.style.display
            }))
        }));
        
        // Store unique values for each column for filter dropdowns
        this.columnValues = {};
        const headerCells = this.table.querySelectorAll('thead th');
        headerCells.forEach((_, colIndex) => {
            const values = new Set();
            this.originalData.forEach(rowData => {
                const cellValue = rowData.cells[colIndex]?.text || '';
                if (cellValue) values.add(cellValue);
            });
            this.columnValues[colIndex] = Array.from(values).sort();
        });
    }

    initSearch() {
        const searchContainer = document.createElement('div');
        searchContainer.className = 'mb-3';
        searchContainer.innerHTML = `
            <div class="input-group">
                <span class="input-group-text">
                    <i class="bi bi-search"></i>
                </span>
                <input type="text" class="form-control" id="table-search" placeholder="Search...">
            </div>
        `;
        
        const searchInput = searchContainer.querySelector('input');
        searchInput.addEventListener('input', (e) => {
            this.filterTable(e.target.value);
            this.currentPage = 1;
            this.render();
        });

        this.table.parentNode.insertBefore(searchContainer, this.table);
    }

    initSorting() {
        const headers = this.table.querySelectorAll('th[data-sort]');
        headers.forEach((header, index) => {
            header.style.cursor = 'pointer';
            header.title = 'Click to sort';
            
            // Add sort indicator
            const indicator = document.createElement('span');
            indicator.className = 'sort-indicator ms-1';
            header.appendChild(indicator);
            
            header.addEventListener('click', () => {
                if (this.sortColumn === index) {
                    this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    this.sortColumn = index;
                    this.sortDirection = 'asc';
                }
                this.sortTable(index);
                this.render();
            });
        });
    }

    initPagination() {
        const footer = this.table.createTFoot();
        const row = footer.insertRow();
        const cell = row.insertCell();
        cell.colSpan = this.table.rows[0].cells.length;
        cell.className = 'p-3';
        
        const pagination = document.createElement('div');
        pagination.className = 'd-flex justify-content-between align-items-center';
        
        // Rows per page selector
        const rowsPerPageDiv = document.createElement('div');
        rowsPerPageDiv.className = 'd-flex align-items-center';
        rowsPerPageDiv.innerHTML = `
            <span class="me-2">Rows per page:</span>
            <select class="form-select form-select-sm" style="width: auto;">
                <option value="10">10</option>
                <option value="25" selected>25</option>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="0">All</option>
            </select>
        `;
        
        const rowsPerPageSelect = rowsPerPageDiv.querySelector('select');
        rowsPerPageSelect.value = this.config.rowsPerPage;
        rowsPerPageSelect.addEventListener('change', (e) => {
            this.config.rowsPerPage = parseInt(e.target.value) || 0;
            this.currentPage = 1;
            this.render();
        });
        
        // Page navigation
        const pageNav = document.createElement('div');
        pageNav.className = 'd-flex align-items-center';
        pageNav.innerHTML = `
            <button class="btn btn-sm btn-outline-secondary me-2" id="first-page">First</button>
            <button class="btn btn-sm btn-outline-secondary me-2" id="prev-page">Previous</button>
            <span id="page-info" class="mx-2">Page 1 of 1</span>
            <button class="btn btn-sm btn-outline-secondary ms-2" id="next-page">Next</button>
            <button class="btn btn-sm btn-outline-secondary ms-2" id="last-page">Last</button>
        `;
        
        // Add event listeners for pagination
        pageNav.querySelector('#first-page').addEventListener('click', () => {
            this.currentPage = 1;
            this.render();
        });
        
        pageNav.querySelector('#prev-page').addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.render();
            }
        });
        
        pageNav.querySelector('#next-page').addEventListener('click', () => {
            const totalPages = this.getTotalPages();
            if (this.currentPage < totalPages) {
                this.currentPage++;
                this.render();
            }
        });
        
        pageNav.querySelector('#last-page').addEventListener('click', () => {
            this.currentPage = this.getTotalPages();
            this.render();
        });
        
        // Assemble the pagination controls
        pagination.appendChild(rowsPerPageDiv);
        pagination.appendChild(pageNav);
        cell.appendChild(pagination);
    }

    initExport() {
        const exportContainer = document.createElement('div');
        exportContainer.className = 'mb-3 d-flex justify-content-end';
        
        const exportBtn = document.createElement('button');
        exportBtn.className = 'btn btn-primary';
        exportBtn.innerHTML = '<i class="bi bi-download me-2"></i>Export';
        
        const dropdownMenu = document.createElement('div');
        dropdownMenu.className = 'dropdown-menu dropdown-menu-end';
        dropdownMenu.setAttribute('aria-labelledby', 'exportDropdown');
        
        // Add export options based on configuration
        if (this.config.exportFormats.includes('csv')) {
            const csvItem = document.createElement('a');
            csvItem.className = 'dropdown-item';
            csvItem.href = '#';
            csvItem.innerHTML = '<i class="bi bi-filetype-csv me-2"></i>Export as CSV';
            csvItem.addEventListener('click', (e) => {
                e.preventDefault();
                this.exportToCSV();
            });
            dropdownMenu.appendChild(csvItem);
        }
        
        if (this.config.exportFormats.includes('excel')) {
            const excelItem = document.createElement('a');
            excelItem.className = 'dropdown-item';
            excelItem.href = '#';
            excelItem.innerHTML = '<i class="bi bi-file-earmark-excel me-2"></i>Export as Excel';
            excelItem.addEventListener('click', (e) => {
                e.preventDefault();
                this.exportToExcel();
            });
            dropdownMenu.appendChild(excelItem);
        }
        
        if (this.config.exportFormats.includes('pdf')) {
            const pdfItem = document.createElement('a');
            pdfItem.className = 'dropdown-item';
            pdfItem.href = '#';
            pdfItem.innerHTML = '<i class="bi bi-file-earmark-pdf me-2"></i>Export as PDF';
            pdfItem.addEventListener('click', (e) => {
                e.preventDefault();
                this.exportToPDF();
            });
            dropdownMenu.appendChild(pdfItem);
        }
        
        if (this.config.exportFormats.includes('print')) {
            const printItem = document.createElement('a');
            printItem.className = 'dropdown-item';
            printItem.href = '#';
            printItem.innerHTML = '<i class="bi bi-printer me-2"></i>Print Table';
            printItem.addEventListener('click', (e) => {
                e.preventDefault();
                this.printTable();
            });
            dropdownMenu.appendChild(printItem);
        }
        
        // Set up the dropdown button
        const dropdownBtn = document.createElement('div');
        dropdownBtn.className = 'dropdown';
        dropdownBtn.innerHTML = `
            <button class="btn btn-primary dropdown-toggle" type="button" id="exportDropdown" 
                    data-bs-toggle="dropdown" aria-expanded="false">
                <i class="bi bi-download me-2"></i>Export
            </button>
        `;
        dropdownBtn.appendChild(dropdownMenu);
        exportContainer.appendChild(dropdownBtn);
        
        // Insert the export controls before the table
        this.table.parentNode.insertBefore(exportContainer, this.table);
    }

    addFilterStyles() {
        // Add styles for filter inputs if not already added
        if (!document.getElementById('enhanced-table-styles')) {
            const style = document.createElement('style');
            style.id = 'enhanced-table-styles';
            style.textContent = `
                .filter-container {
                    position: relative;
                    display: inline-block;
                    width: 100%;
                }
                .filter-input {
                    width: 100%;
                    padding: 4px 8px;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                    font-size: 0.875rem;
                }
                .filter-dropdown {
                    position: absolute;
                    z-index: 1000;
                    background: white;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                    max-height: 200px;
                    overflow-y: auto;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    display: none;
                    min-width: 150px;
                }
                .filter-dropdown.show {
                    display: block;
                }
                .filter-dropdown-item {
                    padding: 6px 12px;
                    cursor: pointer;
                    white-space: nowrap;
                }
                .filter-dropdown-item:hover {
                    background-color: #f8f9fa;
                }
                .filter-dropdown-item input[type="checkbox"] {
                    margin-right: 6px;
                }
                .filter-icon {
                    position: absolute;
                    right: 8px;
                    top: 50%;
                    transform: translateY(-50%);
                    color: #6c757d;
                    cursor: pointer;
                }
                .filter-active {
                    color: #0d6efd;
                }
                .filter-clear {
                    position: absolute;
                    right: 28px;
                    top: 50%;
                    transform: translateY(-50%);
                    color: #6c757d;
                    cursor: pointer;
                    display: none;
                }
                .filter-clear.visible {
                    display: block;
                }
            `;
            document.head.appendChild(style);
        }
    }

    initColumnFilters() {
        const headerCells = this.table.querySelectorAll('thead th');
        
        // Create a filter row if it doesn't exist
        let filterRow = this.table.querySelector('thead tr.filter-row');
        if (!filterRow) {
            filterRow = document.createElement('tr');
            filterRow.className = 'filter-row';
            
            headerCells.forEach((headerCell, index) => {
                const th = document.createElement('th');
                
                // Skip if column has data-no-filter attribute
                if (headerCell.hasAttribute('data-no-filter')) {
                    th.innerHTML = '&nbsp;';
                    filterRow.appendChild(th);
                    return;
                }
                
                const filterContainer = document.createElement('div');
                filterContainer.className = 'filter-container';
                
                // Create filter input
                const filterInput = document.createElement('input');
                filterInput.type = 'text';
                filterInput.className = 'filter-input';
                filterInput.placeholder = 'Filter...';
                filterInput.dataset.columnIndex = index;
                
                // Create clear filter button
                const clearBtn = document.createElement('span');
                clearBtn.className = 'filter-clear';
                clearBtn.innerHTML = '&times;';
                clearBtn.title = 'Clear filter';
                clearBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    filterInput.value = '';
                    this.clearColumnFilter(index);
                    clearBtn.classList.remove('visible');
                });
                
                // Create filter dropdown button
                const filterBtn = document.createElement('span');
                filterBtn.className = 'filter-icon';
                filterBtn.innerHTML = '\u25BE';
                filterBtn.title = 'Filter options';
                
                // Create dropdown menu
                const dropdown = document.createElement('div');
                dropdown.className = 'filter-dropdown';
                
                // Populate dropdown with unique values
                this.populateFilterDropdown(dropdown, index);
                
                // Toggle dropdown
                filterBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    dropdown.classList.toggle('show');
                });
                
                // Handle input filter
                let filterTimeout;
                filterInput.addEventListener('input', (e) => {
                    clearTimeout(filterTimeout);
                    filterTimeout = setTimeout(() => {
                        const value = e.target.value.trim();
                        if (value) {
                            this.applyColumnFilter(index, value);
                            clearBtn.classList.add('visible');
                        } else {
                            this.clearColumnFilter(index);
                            clearBtn.classList.remove('visible');
                        }
                    }, 300);
                });
                
                // Close dropdown when clicking outside
                document.addEventListener('click', (e) => {
                    if (!filterContainer.contains(e.target)) {
                        dropdown.classList.remove('show');
                    }
                });
                
                // Add elements to container
                filterContainer.appendChild(filterInput);
                filterContainer.appendChild(clearBtn);
                filterContainer.appendChild(filterBtn);
                filterContainer.appendChild(dropdown);
                th.appendChild(filterContainer);
                filterRow.appendChild(th);
            });
            
            // Insert filter row after the header row
            const thead = this.table.querySelector('thead');
            const headerRow = thead.querySelector('tr');
            thead.insertBefore(filterRow, headerRow.nextSibling);
        }
    }
    
    populateFilterDropdown(dropdown, columnIndex) {
        const values = this.columnValues[columnIndex] || [];
        dropdown.innerHTML = '';
        
        // Add search input for the dropdown
        const searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.className = 'form-control form-control-sm mb-2';
        searchInput.placeholder = 'Search values...';
        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            const items = dropdown.querySelectorAll('.filter-dropdown-item');
            items.forEach(item => {
                const text = item.textContent.toLowerCase();
                item.style.display = text.includes(searchTerm) ? '' : 'none';
            });
        });
        dropdown.appendChild(searchInput);
        
        // Add select all/none buttons
        const buttonGroup = document.createElement('div');
        buttonGroup.className = 'd-flex justify-content-between mb-2';
        
        const selectAllBtn = document.createElement('button');
        selectAllBtn.className = 'btn btn-sm btn-outline-secondary btn-sm';
        selectAllBtn.textContent = 'Select All';
        selectAllBtn.addEventListener('click', () => {
            const checkboxes = dropdown.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(checkbox => {
                checkbox.checked = true;
            });
        });
        
        const selectNoneBtn = document.createElement('button');
        selectNoneBtn.className = 'btn btn-sm btn-outline-secondary btn-sm';
        selectNoneBtn.textContent = 'Select None';
        selectNoneBtn.addEventListener('click', () => {
            const checkboxes = dropdown.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(checkbox => {
                checkbox.checked = false;
            });
        });
        
        const applyBtn = document.createElement('button');
        applyBtn.className = 'btn btn-sm btn-primary btn-sm';
        applyBtn.textContent = 'Apply';
        applyBtn.addEventListener('click', () => {
            const selectedValues = [];
            const checkboxes = dropdown.querySelectorAll('input[type="checkbox"]:checked');
            checkboxes.forEach(checkbox => {
                selectedValues.push(checkbox.value);
            });
            
            if (selectedValues.length > 0) {
                this.applyMultiSelectFilter(columnIndex, selectedValues);
                const filterInput = this.table.querySelector(`.filter-input[data-column-index="${columnIndex}"]`);
                const clearBtn = filterInput.nextElementSibling;
                filterInput.value = `${selectedValues.length} selected`;
                clearBtn.classList.add('visible');
            }
            
            dropdown.classList.remove('show');
        });
        
        buttonGroup.appendChild(selectAllBtn);
        buttonGroup.appendChild(selectNoneBtn);
        dropdown.appendChild(buttonGroup);
        
        // Add values to dropdown
        const valuesContainer = document.createElement('div');
        valuesContainer.className = 'dropdown-values';
        valuesContainer.style.maxHeight = '150px';
        valuesContainer.style.overflowY = 'auto';
        
        values.forEach(value => {
            const item = document.createElement('div');
            item.className = 'filter-dropdown-item';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = value;
            checkbox.id = `filter-${columnIndex}-${value.replace(/\s+/g, '-')}`;
            
            const label = document.createElement('label');
            label.htmlFor = checkbox.id;
            label.textContent = value;
            label.style.marginLeft = '5px';
            label.style.cursor = 'pointer';
            
            item.appendChild(checkbox);
            item.appendChild(label);
            valuesContainer.appendChild(item);
        });
        
        dropdown.appendChild(valuesContainer);
        dropdown.appendChild(document.createElement('div'));
        dropdown.appendChild(applyBtn);
    }
    
    applyColumnFilter(columnIndex, filterValue) {
        this.columnFilters = this.columnFilters || {};
        this.columnFilters[columnIndex] = filterValue.toLowerCase();
        this.applyFilters();
    }
    
    applyMultiSelectFilter(columnIndex, selectedValues) {
        this.columnFilters = this.columnFilters || {};
        this.columnFilters[columnIndex] = selectedValues;
        this.applyFilters();
    }
    
    clearColumnFilter(columnIndex) {
        if (this.columnFilters && this.columnFilters[columnIndex]) {
            delete this.columnFilters[columnIndex];
            this.applyFilters();
        }
    }
    
    applyFilters() {
        this.filteredData = this.originalData.filter(row => {
            // Check if row matches all column filters
            for (const [columnIndex, filterValue] of Object.entries(this.columnFilters || {})) {
                const colIndex = parseInt(columnIndex);
                const cellValue = row.cells[colIndex]?.text?.toLowerCase() || '';
                
                if (Array.isArray(filterValue)) {
                    // Multi-select filter
                    if (!filterValue.some(val => cellValue === val.toLowerCase())) {
                        return false;
                    }
                } else if (!cellValue.includes(filterValue)) {
                    // Text filter
                    return false;
                }
            }
            return true;
        });
        
        // Reset to first page when filters change
        this.currentPage = 1;
        this.render();
    }
    
    filterTable(searchTerm) {
        this.globalSearchTerm = searchTerm ? searchTerm.toLowerCase() : '';
        this.applyFilters();
    }

    sortTable(columnIndex, initialSort = false) {
        if (columnIndex === null || columnIndex === undefined) return;
        
        // Update sort indicators
        const headers = this.table.querySelectorAll('th[data-sort]');
        headers.forEach((header, index) => {
            const indicator = header.querySelector('.sort-indicator');
            if (!indicator) return;
            
            if (index === columnIndex) {
                indicator.innerHTML = this.sortDirection === 'asc' ? '↑' : '↓';
                header.setAttribute('data-sort-direction', this.sortDirection);
            } else {
                indicator.innerHTML = '';
                header.removeAttribute('data-sort-direction');
            }
        });
        
        // Sort the data
        this.filteredData.sort((a, b) => {
            const aValue = a.cells[columnIndex]?.sortValue || '';
            const bValue = b.cells[columnIndex]?.sortValue || '';
            
            // Check for numeric sorting
            const isNumeric = !isNaN(parseFloat(aValue)) && isFinite(aValue) && 
                             !isNaN(parseFloat(bValue)) && isFinite(bValue);
            
            let comparison = 0;
            
            if (isNumeric) {
                comparison = parseFloat(aValue) - parseFloat(bValue);
            } else if (aValue > bValue) {
                comparison = 1;
            } else if (aValue < bValue) {
                comparison = -1;
            }
            
            return this.sortDirection === 'asc' ? comparison : -comparison;
        });
        
        if (!initialSort) {
            this.currentPage = 1;
        }
    }

    getTotalPages() {
        if (this.config.rowsPerPage <= 0) return 1;
        return Math.ceil(this.filteredData.length / this.config.rowsPerPage);
    }

    getCurrentPageData() {
        if (this.config.rowsPerPage <= 0) {
            return this.filteredData;
        }
        
        const startIndex = (this.currentPage - 1) * this.config.rowsPerPage;
        const endIndex = startIndex + this.config.rowsPerPage;
        return this.filteredData.slice(startIndex, endIndex);
    }

    render() {
        // Update pagination info
        const totalPages = this.getTotalPages();
        const pageInfo = this.table.querySelector('#page-info');
        if (pageInfo) {
            pageInfo.textContent = `Page ${this.currentPage} of ${totalPages}`;
        }
        
        // Update pagination buttons
        const firstPageBtn = this.table.querySelector('#first-page');
        const prevPageBtn = this.table.querySelector('#prev-page');
        const nextPageBtn = this.table.querySelector('#next-page');
        const lastPageBtn = this.table.querySelector('#last-page');
        
        if (firstPageBtn) firstPageBtn.disabled = this.currentPage === 1;
        if (prevPageBtn) prevPageBtn.disabled = this.currentPage === 1;
        if (nextPageBtn) nextPageBtn.disabled = this.currentPage >= totalPages;
        if (lastPageBtn) lastPageBtn.disabled = this.currentPage >= totalPages;
        
        // Show/hide rows based on pagination
        const tbody = this.table.querySelector('tbody');
        if (!tbody) return;
        
        // Clear existing rows
        while (tbody.firstChild) {
            tbody.removeChild(tbody.firstChild);
        }
        
        // Add filtered and paginated rows
        const currentPageData = this.getCurrentPageData();
        currentPageData.forEach(rowData => {
            tbody.appendChild(rowData.element);
        });
        
        // Show a message if no data is available
        if (this.filteredData.length === 0) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = this.table.rows[0]?.cells.length || 1;
            td.className = 'text-center py-4 text-muted';
            td.textContent = 'No data available';
            tr.appendChild(td);
            tbody.appendChild(tr);
        }
    }

    // Export methods
    exportToCSV() {
        const headers = [];
        const rows = [];
        
        // Get headers
        this.table.querySelectorAll('thead th').forEach(header => {
            if (header.style.display !== 'none') {
                headers.push(`"${header.textContent.trim().replace(/"/g, '""')}"`);
            }
        });
        
        // Get rows
        this.filteredData.forEach(rowData => {
            const row = [];
            rowData.cells.forEach((cell, index) => {
                const header = this.table.rows[0]?.cells[index];
                if (header && header.style.display !== 'none') {
                    row.push(`"${cell.text.replace(/"/g, '""')}"`);
                }
            });
            rows.push(row.join(','));
        });
        
        // Create CSV content
        const csvContent = [
            headers.join(','),
            ...rows
        ].join('\n');
        
        // Create and trigger download
        this.downloadFile(csvContent, `${this.config.exportFileName}.csv`, 'text/csv;charset=utf-8;');
    }

    exportToExcel() {
        // For Excel export, we'll use the CSV method with an .xls extension
        // Note: For full Excel support, you might want to use a library like SheetJS
        this.exportToCSV();
        return;
        
        // The following is a placeholder for actual Excel export implementation
        /*
        const wb = XLSX.utils.book_new();
        const ws = XLSX.utils.table_to_sheet(this.table);
        XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
        XLSX.writeFile(wb, `${this.config.exportFileName}.xlsx`);
        */
    }

    exportToPDF() {
        // For PDF export, we'll open a print dialog
        // For more advanced PDF generation, consider using a library like jsPDF or pdfmake
        this.printTable();
    }

    printTable() {
        const printWindow = window.open('', '_blank');
        printWindow.document.write(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>${this.config.exportOptions.title}</title>
                <style>
                    @media print {
                        @page {
                            size: ${this.config.exportOptions.pageSize} ${this.config.exportOptions.orientation};
                            margin: ${this.config.exportOptions.margin};
                        }
                        body { font-family: Arial, sans-serif; }
                        h1 { text-align: center; margin-bottom: 20px; }
                        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
                        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                        th { background-color: #f2f2f2; }
                        .no-print { display: none; }
                    }
                </style>
            </head>
            <body>
                <h1>${this.config.exportOptions.title}</h1>
                <div id="table-container"></div>
                <script>
                    // Clone the table and clean it up for printing
                    const table = window.opener.document.querySelector('table#${this.table.id}').cloneNode(true);
                    
                    // Remove action buttons and other non-essential elements
                    table.querySelectorAll('.no-print, .dropdown, .btn, [data-bs-toggle]').forEach(el => el.remove());
                    
                    // Add to the print window
                    document.getElementById('table-container').appendChild(table);
                    
                    // Print and close
                    window.onload = function() {
                        window.print();
                        // window.onafterprint = function() { window.close(); };
                    };
                <\/script>
            </body>
            </html>
        `);
        printWindow.document.close();
    }

    downloadFile(content, fileName, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        
        // Cleanup
        setTimeout(() => {
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        }, 0);
    }

    // Public methods
    refresh() {
        this.cacheOriginalData();
        this.filteredData = [...this.originalData];
        this.render();
    }
}

// Auto-initialize tables with the 'enhanced-table' class
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('table.enhanced-table').forEach(table => {
        // Check if Django pagination exists (look for pagination controls in the page)
        const hasDjangoPagination = document.querySelector('.pagination');
        
        // If Django pagination exists, disable JavaScript pagination
        new EnhancedTable({ 
            table,
            pagination: !hasDjangoPagination  // Disable JS pagination if Django handles it
        });
    });
});

// Make EnhancedTable available globally
window.EnhancedTable = EnhancedTable;
