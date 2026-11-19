# Scholar Tracker Web Prototype

This is the first browser-based prototype for Scholar Tracker, a school management project focused on reducing truancy and helping teachers, school administrators, and parents stay informed.

## Included in this prototype

- Overview dashboard and attendance summary
- Daily attendance register with Present, Absent, and Unmarked states
- Add and search demo student records
- Class and stream directory
- Parent portal preview
- School event calendar
- Attendance report with CSV export
- Responsive layout for desktop and mobile

## Run it

Open `index.html` in a modern browser, or serve the `web` directory with any static web server.

## Publish with GitHub Pages

The workflow at `.github/workflows/scholar-tracker-pages.yml` publishes the `web/` directory when it changes on `main`.

1. Open the repository's **Settings → Pages**.
2. If asked for a source, select **GitHub Actions**.
3. Open the **Actions** tab and check **Publish Scholar Tracker web demo**.
4. When deployment succeeds, open the URL shown in the workflow's deployment environment.

## Important limitations

This is a frontend prototype, not a production school system. Sample records and changes are stored in the current browser using local storage. They are not shared with other devices, and clearing browser data may erase them. There is no real authentication, server database, SMS/email notification, access control, or verified parent-child linking yet. Do not enter real student personal information until a secure backend and privacy protections have been implemented.

The existing Python project at the repository root is preserved; this web prototype lives in its own `web/` folder.