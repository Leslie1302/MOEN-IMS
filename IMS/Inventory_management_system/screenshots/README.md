# Screenshots Directory

This directory is used by the Weekly Report System to automatically include screenshots in generated reports.

## How It Works

When you generate a weekly report, the system automatically:
1. Scans this directory for image files
2. Finds screenshots modified within the report period
3. Categorizes them by filename
4. Includes up to 5 screenshots in the PDF attachment
5. Lists them in the email body

## Naming Conventions

Use descriptive filenames to help the system categorize your screenshots:

### Features
- `feature_user_login.png`
- `new_dashboard_layout.png`
- `add_inventory_form.png`

### Bug Fixes
- `bug_fix_authentication.png`
- `fix_error_page.png`
- `error_resolved_display.png`

### UI Changes
- `ui_redesign_homepage.png`
- `interface_update_menu.png`
- `design_new_theme.png`

### Dashboard
- `dashboard_overview.png`
- `home_page_update.png`
- `main_screen.png`

### Reports
- `report_analytics_chart.png`
- `chart_sales_data.png`
- `graph_inventory_levels.png`

## Supported Formats

- PNG (`.png`) - Recommended
- JPEG (`.jpg`, `.jpeg`)
- GIF (`.gif`)
- WebP (`.webp`)
- SVG (`.svg`)

## Best Practices

1. **Use descriptive names**: `feature_signature_lookup.png` instead of `screenshot1.png`
2. **Keep file sizes reasonable**: Compress large images (< 2 MB per file)
3. **Use PNG for UI**: Better quality for interface screenshots
4. **Use JPEG for photos**: Smaller file size for photographic content
5. **Date in filename (optional)**: `2025-11-06_feature_new_report.png`

## Example Structure

```
screenshots/
├── feature_digital_signatures.png
├── feature_weekly_reports.png
├── bug_fix_template_error.png
├── ui_dashboard_redesign.png
├── dashboard_main_view.png
└── report_inventory_chart.png
```

## Tips

- Take screenshots as you complete features
- Capture before/after for bug fixes
- Include relevant UI elements (menus, buttons, etc.)
- Annotate screenshots if needed (arrows, highlights)
- Delete old screenshots periodically to keep directory clean

## Automatic Inclusion

Screenshots are automatically included if:
- ✅ Located in this directory (or subdirectories)
- ✅ Modified within the report period (e.g., last 7 days)
- ✅ Have a supported file extension
- ✅ File is readable and not corrupted

## Manual Inclusion

To manually reference screenshots in custom notes:
1. Save screenshot to this directory
2. Add note in report generation form: "See screenshot: feature_name.png"
3. Screenshot will be automatically included in PDF

## Questions?

See `WEEKLY_REPORT_GUIDE.md` in the project root for more information.
