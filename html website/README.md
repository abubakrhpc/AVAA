# AVAA Web Demo

AVAA is a child-friendly smart companion demo site with:
- Home, About, Live Monitoring, and Companion pages
- Simulated safety status + alerts
- Emergency stop concept
- Responsive layout for desktop, tablet, and mobile

## Robot Image

The app auto-searches for a robot image in the project root, in this order:
1. `avaa.png`
2. `robot.png`
3. `robot.jpg`
4. `robot.jpeg`
5. `robot.webp`

To use your own image, place it in this folder with any of those names.

## Run locally

No build step required.

- Option 1: Open `index.html` directly in a browser.
- Option 2 (recommended): use VS Code Live Server extension.

## Deploy and share

### Option A: Netlify (fastest)
1. Create a GitHub repo and push this folder.
2. Go to Netlify -> Add new site -> Import from Git.
3. Build command: *(leave empty)*
4. Publish directory: `.`
5. Deploy.

### Option B: Vercel
1. Push this folder to GitHub.
2. Import project in Vercel.
3. Framework preset: `Other`.
4. Build command: *(leave empty)*
5. Output directory: *(leave empty)*
6. Deploy.

### Option C: GitHub Pages
1. Push files to a repository.
2. In GitHub: Settings -> Pages.
3. Source: `Deploy from a branch`.
4. Branch: `main` (root folder).
5. Save and wait for the generated URL.

## Notes

- This is a prototype/demo frontend.
- Live monitoring data and alerts are simulated in `app.js`.
