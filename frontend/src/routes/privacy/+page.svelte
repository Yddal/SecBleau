<svelte:head>
  <title>SecBleau — Privacy Notice</title>
</svelte:head>

<div class="page">
  <header class="header">
    <a class="logo" href="/">
      <span class="logo-sec">Sec</span><span class="logo-bleau">Bleau</span>
    </a>
    <div class="tagline">Privacy Notice</div>
    <a class="nav-link" href="/">← Map</a>
    <a class="nav-link" href="/about">About</a>
  </header>

  <main class="content">

    <p class="updated">Last updated: March 2026</p>

    <section class="card">
      <h2>Summary</h2>
      <p>
        SecBleau does not collect, store, or share any personal information that could
        identify you. No accounts, no cookies, no tracking pixels, no analytics services.
      </p>
    </section>

    <section class="card">
      <h2>What data is collected and why</h2>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Data</th>
              <th>How it is handled</th>
              <th>Purpose</th>
              <th>Retained</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>IP address + browser type</td>
              <td>Combined and hashed with SHA-256 immediately. The original values are never stored.</td>
              <td>Rate-limiting: prevents the same device from submitting duplicate condition reports within 4 hours.</td>
              <td>1 year from submission, then deleted</td>
            </tr>
            <tr>
              <td>Condition report (wet / drying / climbable)</td>
              <td>Stored as plain text alongside the hash above.</td>
              <td>Improves dryness predictions for that boulder or area.</td>
              <td>1 year from submission, then deleted</td>
            </tr>
            <tr>
              <td>Optional notes field</td>
              <td>Free text, stored as-is. Do not enter personal information here.</td>
              <td>Additional context for the report.</td>
              <td>1 year from submission, then deleted</td>
            </tr>
            <tr>
              <td>Device location (GPS)</td>
              <td>Used only in your browser to centre the map. Never sent to the server.</td>
              <td>Map navigation.</td>
              <td>Never stored</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="card">
      <h2>Legal basis (GDPR)</h2>
      <p>
        SecBleau is operated as a non-commercial hobby project with no revenue. The minimal
        data processing described above is carried out under <strong>legitimate interest</strong>
        (Article 6(1)(f) GDPR): preventing abuse of the reporting system and improving the
        accuracy of rock condition predictions — a service that benefits the climbing community
        and causes no harm to individuals.
      </p>
      <p>
        The SHA-256 hash of IP + browser type is a derived, one-way value. It cannot be
        reversed to recover the original IP address and does not meet the definition of
        personal data under Recital 26 GDPR ("reasonably likely to identify"). Nevertheless,
        it is deleted after one year as a precaution.
      </p>
    </section>

    <section class="card">
      <h2>Third-party services</h2>
      <ul>
        <li>
          <strong>Open-Meteo</strong> — weather API. When fetching forecasts,
          the geographic coordinates of climbing areas (not your location) are sent.
          <a href="https://open-meteo.com/en/terms" target="_blank" rel="noopener">Their terms</a>.
        </li>
        <li>
          <strong>OpenFreeMap / OpenStreetMap</strong> — map tiles. Your browser requests
          map tile images directly; standard web server logs may apply.
          <a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> ·
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OSM copyright</a>.
        </li>
        <li>
          <strong>Météoblue</strong> — linked for historical weather reference only.
          Clicking those links takes you to their site under their own privacy policy.
        </li>
      </ul>
    </section>

    <section class="card">
      <h2>Your rights</h2>
      <p>
        Because no data is stored that can identify you, rights to access, rectification,
        portability, or erasure of <em>your specific data</em> cannot be exercised in the
        traditional sense — there is no way to link a stored hash back to you.
      </p>
      <p>
        All condition reports and associated hashes are automatically deleted after one year.
        If you have any questions or concerns, you can reach out via the project's
        issue tracker.
      </p>
    </section>

    <section class="card">
      <h2>Changes to this notice</h2>
      <p>
        If data practices change materially, this page will be updated and the date above revised.
        This project does not send email newsletters or notifications.
      </p>
    </section>

  </main>
</div>

<style>
  :global(html), :global(body) { overflow: auto !important; height: auto !important; }

  .page { min-height: 100vh; background: #f8fafc; }

  .header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 20px;
    height: 48px;
    background: #111827;
    color: #fff;
    position: sticky;
    top: 0;
    z-index: 10;
  }
  .logo { font-size: 20px; font-weight: 900; letter-spacing: -0.03em; text-decoration: none; }
  .logo-sec { color: #a6d96a; }
  .logo-bleau { color: #fff; }
  .tagline { font-size: 13px; color: #9ca3af; flex: 1; }
  .nav-link { color: #9ca3af; font-size: 12px; text-decoration: none; }
  .nav-link:hover { color: #fff; }

  .content {
    max-width: 720px;
    margin: 0 auto;
    padding: 28px 16px 60px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .updated { font-size: 11px; color: #9ca3af; margin-bottom: 4px; }

  .card {
    background: #fff;
    border-radius: 12px;
    padding: 20px 24px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
  }
  .card h2 { font-size: 15px; font-weight: 700; color: #111; margin-bottom: 12px; }
  .card p { font-size: 13px; color: #374151; line-height: 1.6; margin-bottom: 10px; }
  .card p:last-child { margin-bottom: 0; }
  .card ul { font-size: 13px; color: #374151; line-height: 1.8; padding-left: 20px; }
  .card a { color: #2563eb; }
  .card a:hover { text-decoration: underline; }

  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th {
    background: #f3f4f6;
    text-align: left;
    padding: 8px 10px;
    font-weight: 700;
    color: #111;
    white-space: nowrap;
  }
  td { padding: 8px 10px; border-top: 1px solid #f3f4f6; color: #374151; vertical-align: top; line-height: 1.5; }
  tr:last-child td { border-bottom: 1px solid #f3f4f6; }
</style>
