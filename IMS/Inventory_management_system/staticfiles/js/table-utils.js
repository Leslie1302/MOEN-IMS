// Enhanced table filtering and utilities
class TableUtils {
    constructor(tableId, options = {}) {
        this.table = document.getElementById(tableId);
        if (!this.table) {
            console.error(`Table with ID '${tableId}' not found`);
            return;
        }

        // Default options
        this.options = {
            searchInputId: options.searchInputId || 'table-search',
            searchColumns: options.searchColumns || 'all', // 'all' or array of column indices
            pagination: options.pagination !== false,
            rowsPerPage: options.rowsPerPage || 25,
            exportButtons: options.exportButtons !== false,
            columnFilters: options.columnFilters !== false,
            stickyHeader: options.stickyHeader !== false,
            ...options
        };

        this.rows = Array.from(this.table.querySelectorAll('tbody tr'));
        this.currentPage = 1;
        this.filteredRows = [];
        this.filters = {};
        this.sortConfig = { column: null, direction: 'asc' };

        this.init();
    }

    init() {
        // Initialize table features
        if (this.options.stickyHeader) this.makeHeaderSticky();
        if (this.options.columnFilters) this.initColumnFilters();
        if (this.options.searchInputId) this.initGlobalSearch();
        if (this.options.pagination) this.initPagination();
        if (this.options.exportButtons) this.initExportButtons();
        
        // Initialize sorting
        this.initSorting();
        
        // Initial filter
        this.filterTable();
    }

    makeHeaderSticky() {
        const thead = this.table.querySelector('thead');
        if (thead) {
            thead.classList.add('sticky-top', 'bg-light');
            // Add a small shadow for better visibility
            thead.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1)';
        }
    }

    initGlobalSearch() {
        let searchInput = document.getElementById(this.options.searchInputId);
        
        // Create search input if it doesn't exist
        if (!searchInput) {
            const searchContainer = document.createElement('div');
            searchContainer.className = 'mb-3';
            searchContainer.innerHTML = `
                <div class="input-group">
                    <span class="input-group-text">
                        <i class="bi bi-search"></i>
                    </span>
                    <input type="text" class="form-control" id="${this.options.searchInputId}" 
                           placeholder="Search in table...">
                    <button class="btn btn-outline-secondary clear-search" type="button">
                        <i class="bi bi-x-lg"></i>
                    </button>
                </div>
            `;
            this.table.parentNode.insertBefore(searchContainer, this.table);
            searchInput = document.getElementById(this.options.searchInputId);
        }

        // Add search event
        searchInput.addEventListener('input', (e) => {
            this.searchTable(e.target.value);
        });

        // Add clear search button event
        const clearBtn = searchInput.closest('.input-group').querySelector('.clear-search');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                searchInput.value = '';
                this.searchTable('');
            });
        }
    }

    initColumnFilters() {
        const headers = this.table.querySelectorAll('th[data-column]');
        headers.forEach(header => {
            const colIndex = parseInt(header.getAttribute('data-column'));
            
            // Add filter icon
            if (!header.querySelector('.filter-icon')) {
                const filterIcon = document.createElement('span');
                filterIcon.className = 'filter-icon ms-1';
                filterIcon.innerHTML = '🔍';
                filterIcon.style.cursor = 'pointer';
                header.appendChild(filterIcon);

                // Create filter dropdown
                const dropdown = document.createElement('div');
                dropdown.className = 'dropdown-menu p-2 filter-dropdown';
                dropdown.style.minWidth = '200px';
                dropdown.innerHTML = `
                    <div class="mb-2">
                        <input type="text" class="form-control form-control-sm mb-2" 
                               placeholder="Filter..." data-filter-input>
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" 
                                   id="filterExactMatch${colIndex}" data-filter-exact>
                            <label class="form-check-label small" for="filterExactMatch${colIndex}">
                                Exact match
                            </label>
                        </div>
                    </div>
                    <div class="filter-options" style="max-height: 200px; overflow-y: auto;">
                        <!-- Options will be populated here -->
                    </div>
                    <div class="d-flex justify-content-between mt-2">
                        <button class="btn btn-sm btn-outline-secondary" data-filter-clear>
                            Clear
                        </button>
                        <button class="btn btn-sm btn-primary" data-filter-apply>
                            Apply
                        </button>
                    </div>
                `;
                document.body.appendChild(dropdown);

                // Toggle dropdown
                filterIcon.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.toggleFilterDropdown(dropdown, header);
                });

                // Initialize filter functionality
                this.initColumnFilterEvents(dropdown, colIndex);
            }
        });
    }

    initColumnFilterEvents(dropdown, colIndex) {
        const filterInput = dropdown.querySelector('[data-filter-input]');
        const exactMatch = dropdown.querySelector('[data-filter-exact]');
        const clearBtn = dropdown.querySelector('[data-filter-clear]');
        const applyBtn = dropdown.querySelector('[data-filter-apply]');
        const optionsContainer = dropdown.querySelector('.filter-options');

        // Populate filter options
        this.populateFilterOptions(colIndex, optionsContainer);

        // Filter options on input
        filterInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            const options = optionsContainer.querySelectorAll('.form-check');
            
            options.forEach(option => {
                const text = option.textContent.trim().toLowerCase();
                const matches = text.includes(searchTerm);
                option.style.display = matches ? '' : 'none';
            });
        });

        // Clear filter
        clearBtn.addEventListener('click', () => {
            optionsContainer.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = false;
            });
            this.clearFilter(colIndex);
            dropdown.style.display = 'none';
        });

        // Apply filter
        applyBtn.addEventListener('click', () => {
            const selectedOptions = [];
            optionsContainer.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
                selectedOptions.push(checkbox.value);
            });

            if (selectedOptions.length > 0) {
                this.filters[colIndex] = {
                    values: selectedOptions,
                    exact: exactMatch.checked
                };
                this.filterTable();
            } else {
                this.clearFilter(colIndex);
            }

            dropdown.style.display = 'none';
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!dropdown.contains(e.target) && !e.target.closest('.filter-icon')) {
                dropdown.style.display = 'none';
            }
        });
    }

    populateFilterOptions(colIndex, container) {
        const values = new Set();
        const rows = this.table.querySelectorAll('tbody tr');
        
        rows.forEach(row => {
            const cell = row.cells[colIndex];
            if (cell) {
                values.add(cell.textContent.trim() || 'N/A');
            }
        });

        container.innerHTML = '';
        Array.from(values).sort().forEach(value => {
            const option = document.createElement('div');
            option.className = 'form-check';
            option.innerHTML = `
                <input class="form-check-input" type="checkbox" value="${value}" 
                       id="filter-${colIndex}-${value.replace(/\s+/g, '-').toLowerCase()}">
                <label class="form-check-label w-100" for="filter-${colIndex}-${value.replace(/\s+/g, '-').toLowerCase()}">
                    ${value}
                </label>
            `;
            container.appendChild(option);
        });
    }

    toggleFilterDropdown(dropdown, header) {
        // Hide all other dropdowns
        document.querySelectorAll('.filter-dropdown').forEach(d => {
            if (d !== dropdown) d.style.display = 'none';
        });

        // Toggle current dropdown
        if (dropdown.style.display === 'block') {
            dropdown.style.display = 'none';
        } else {
            // Position dropdown below header
            const rect = header.getBoundingClientRect();
            dropdown.style.position = 'absolute';
            dropdown.style.top = `${rect.bottom + window.scrollY}px`;
            dropdown.style.left = `${rect.left + window.scrollX}px`;
            dropdown.style.display = 'block';
            
            // Focus search input
            const searchInput = dropdown.querySelector('input[type="text"]');
            if (searchInput) searchInput.focus();
        }
    }

    initSorting() {
        const headers = this.table.querySelectorAll('th[data-sort]');
        headers.forEach(header => {
            header.style.cursor = 'pointer';
            header.addEventListener('click', () => {
                const columnIndex = parseInt(header.getAttribute('data-sort')) || 
                                  Array.from(header.parentNode.children).indexOf(header);
                this.sortTable(columnIndex);
            });
        });
    }

    sortTable(columnIndex) {
        const direction = this.sortConfig.column === columnIndex && 
                         this.sortConfig.direction === 'asc' ? 'desc' : 'asc';
        
        this.sortConfig = { column: columnIndex, direction };
        this.filteredRows.sort((a, b) => {
            const aValue = a.cells[columnIndex]?.textContent.trim().toLowerCase() || '';
            const bValue = b.cells[columnIndex]?.textContent.trim().toLowerCase() || '';
            
            // Try to convert to numbers for numeric comparison
            const aNum = parseFloat(aValue.replace(/[^0-9.-]+/g, ''));
            const bNum = parseFloat(bValue.replace(/[^0-9.-]+/g, ''));
            
            if (!isNaN(aNum) && !isNaN(bNum)) {
                return direction === 'asc' ? aNum - bNum : bNum - aNum;
            }
            
            // Fall back to string comparison
            return direction === 'asc' 
                ? aValue.localeCompare(bValue) 
                : bValue.localeCompare(aValue);
        });
        
        this.updateTable();
        this.updateSortIndicators(columnIndex, direction);
    }

    updateSortIndicators(columnIndex, direction) {
        // Remove all sort indicators
        this.table.querySelectorAll('th').forEach(th => {
            th.classList.remove('sort-asc', 'sort-desc');
            const icon = th.querySelector('.sort-icon');
            if (icon) icon.remove();
        });
        
        // Add sort indicator to current column
        const header = this.table.querySelector(`th:nth-child(${columnIndex + 1})`);
        if (header) {
            const sortIcon = document.createElement('span');
            sortIcon.className = 'sort-icon ms-1';
            sortIcon.innerHTML = direction === 'asc' ? '↑' : '↓';
            header.appendChild(sortIcon);
            header.classList.add(`sort-${direction}`);
        }
    }

    searchTable(term) {
        this.searchTerm = term.toLowerCase();
        this.filterTable();
    }

    filterTable() {
        this.filteredRows = Array.from(this.rows);
        
        // Apply search term filter
        if (this.searchTerm) {
            this.filteredRows = this.filteredRows.filter(row => {
                return Array.from(row.cells).some(cell => {
                    const cellText = cell.textContent.toLowerCase();
                    return cellText.includes(this.searchTerm);
                });
            });
        }
        
        // Apply column filters
        Object.entries(this.filters).forEach(([colIndex, filter]) => {
            const index = parseInt(colIndex);
            this.filteredRows = this.filteredRows.filter(row => {
                const cell = row.cells[index];
                if (!cell) return false;
                
                const cellValue = cell.textContent.trim();
                return filter.values.some(value => 
                    filter.exact 
                        ? cellValue === value
                        : cellValue.toLowerCase().includes(value.toLowerCase())
                );
            });
        });
        
        // Apply sorting if configured
        if (this.sortConfig.column !== null) {
            this.sortTable(this.sortConfig.column);
        } else {
            this.updateTable();
        }
    }

    clearFilter(columnIndex) {
        delete this.filters[columnIndex];
        this.filterTable();
    }

    updateTable() {
        const tbody = this.table.querySelector('tbody');
        if (!tbody) return;
        
        // Clear existing rows
        tbody.innerHTML = '';
        
        // Add filtered rows
        this.filteredRows.forEach(row => {
            tbody.appendChild(row);
        });
        
        // Update row count display if it exists
        const rowCountDisplay = document.getElementById('row-count');
        if (rowCountDisplay) {
            rowCountDisplay.textContent = `Showing ${this.filteredRows.length} of ${this.rows.length} rows`;
        }
        
        // Update pagination if enabled
        if (this.options.pagination) {
            this.updatePagination();
        }
    }

    initPagination() {
        // Implementation for pagination
        // This is a simplified version - you can expand it as needed
        const paginationContainer = document.createElement('div');
        paginationContainer.className = 'd-flex justify-content-between align-items-center mt-3';
        paginationContainer.innerHTML = `
            <div class="small text-muted" id="row-count">
                Showing ${Math.min(this.filteredRows.length, this.options.rowsPerPage)} of ${this.filteredRows.length} rows
            </div>
            <div class="btn-group">
                <button class="btn btn-sm btn-outline-secondary" id="prev-page" disabled>
                    Previous
                </button>
                <button class="btn btn-sm btn-outline-secondary" id="next-page" 
                        ${this.filteredRows.length <= this.options.rowsPerPage ? 'disabled' : ''}>
                    Next
                </button>
            </div>
        `;
        
        this.table.parentNode.insertBefore(paginationContainer, this.table.nextSibling);
        
        // Add event listeners for pagination
        document.getElementById('prev-page').addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.updateTable();
            }
        });
        
        document.getElementById('next-page').addEventListener('click', () => {
            const maxPage = Math.ceil(this.filteredRows.length / this.options.rowsPerPage);
            if (this.currentPage < maxPage) {
                this.currentPage++;
                this.updateTable();
            }
        });
    }

    updatePagination() {
        const prevBtn = document.getElementById('prev-page');
        const nextBtn = document.getElementById('next-page');
        const maxPage = Math.ceil(this.filteredRows.length / this.options.rowsPerPage);
        
        if (prevBtn) {
            prevBtn.disabled = this.currentPage === 1;
        }
        
        if (nextBtn) {
            nextBtn.disabled = this.currentPage >= maxPage || this.filteredRows.length <= this.options.rowsPerPage;
        }
        
        // Update row count display
        const rowCountDisplay = document.getElementById('row-count');
        if (rowCountDisplay) {
            const start = (this.currentPage - 1) * this.options.rowsPerPage + 1;
            const end = Math.min(start + this.options.rowsPerPage - 1, this.filteredRows.length);
            rowCountDisplay.textContent = `Showing ${start}-${end} of ${this.filteredRows.length} rows`;
        }
        
        // Show only current page rows
        const startIndex = (this.currentPage - 1) * this.options.rowsPerPage;
        const endIndex = startIndex + this.options.rowsPerPage;
        const rows = this.table.querySelectorAll('tbody tr');
        
        rows.forEach((row, index) => {
            row.style.display = (index >= startIndex && index < endIndex) ? '' : 'none';
        });
    }

    initExportButtons() {
        // Implementation for export buttons (CSV, Excel, etc.)
        // This is a placeholder - you can implement actual export functionality
        const exportContainer = document.createElement('div');
        exportContainer.className = 'd-flex justify-content-end mb-2';
        exportContainer.innerHTML = `
            <div class="btn-group">
                <button class="btn btn-sm btn-outline-secondary" data-export="csv">
                    <i class="bi bi-file-earmark-spreadsheet"></i> Export CSV
                </button>
                <button class="btn btn-sm btn-outline-secondary" data-export="excel">
                    <i class="bi bi-file-earmark-excel"></i> Export Excel
                </button>
                <button class="btn btn-sm btn-outline-secondary" data-export="print">
                    <i class="bi bi-printer"></i> Print
                </button>
            </div>
        `;
        
        this.table.parentNode.insertBefore(exportContainer, this.table);
        
        // Add export event listeners
        exportContainer.querySelector('[data-export="csv"]').addEventListener('click', () => {
            this.exportToCSV();
        });
        
        exportContainer.querySelector('[data-export="excel"]').addEventListener('click', () => {
            this.exportToExcel();
        });
        
        exportContainer.querySelector('[data-export="print"]').addEventListener('click', () => {
            window.print();
        });
    }

    exportToCSV() {
        // Implementation for CSV export
        const headers = [];
        const rows = [];
        
        // Get headers
        this.table.querySelectorAll('thead th').forEach(th => {
            headers.push(`"${th.textContent.trim().replace(/"/g, '""')}"`);
        });
        
        // Get rows
        this.filteredRows.forEach(row => {
            const rowData = [];
            row.querySelectorAll('td').forEach(cell => {
                rowData.push(`"${cell.textContent.trim().replace(/"/g, '""')}"`);
            });
            rows.push(rowData.join(','));
        });
        
        // Create CSV content
        const csvContent = [
            headers.join(','),
            ...rows
        ].join('\n');
        
        // Download file
        this.downloadFile(csvContent, 'table-export.csv', 'text/csv');
    }

    exportToExcel() {
        // For Excel export, we'll use the same CSV content but with .xls extension
        // Note: For full Excel support, you might want to use a library like SheetJS
        this.exportToCSV(); // For now, just export as CSV with .xls extension
    }

    downloadFile(content, fileName, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
}

// Initialize all tables with the 'enhanced-table' class
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.enhanced-table').forEach(table => {
        new TableUtils(table.id, {
            searchInputId: `${table.id}-search`,
            pagination: true,
            exportButtons: true,
            columnFilters: true,
            stickyHeader: true,
            rowsPerPage: 25
        });
    });
});
