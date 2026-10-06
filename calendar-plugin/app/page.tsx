export default function Home() {
  return <main className="min-h-screen bg-[#101827] text-[#edf2fa] p-6 sm:p-12">
    <div className="mx-auto max-w-2xl">
      <p className="text-sm font-medium text-[#9ba9c3] mb-8">PRIVATE CALENDAR CONNECTION</p>
      <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mb-5">My Proton Calendar</h1>
      <p className="text-lg leading-relaxed text-[#c7d2e6]">Read your calendar and manage appointments from ChatGPT on your phone. Your Proton login stays on your NAS.</p>
      <section className="mt-10 rounded-xl border border-[#34425b] bg-[#19243a] p-6">
        <h2 className="text-xl font-semibold mb-3">Connect your calendar service</h2>
        <p className="text-base leading-relaxed text-[#c7d2e6]">The plugin is prepared. Calendar writes become available after you deploy the Docker adapter on TrueNAS and configure its connection in Sites settings.</p>
        <ol className="list-decimal pl-5 mt-5 space-y-4 text-base leading-relaxed">
          <li>Install or update the TrueNAS App using the project’s YAML, then complete Proton login.</li>
          <li>Configure the adapter’s public HTTPS URL and API key in Sites settings. Keep passwords and API keys out of chat.</li>
          <li>Install this private plugin in ChatGPT, connect your account, and ask it to check the calendar connection.</li>
          <li>Create a disposable test appointment and confirm it appears in Proton Calendar.</li>
        </ol>
      </section>
      <p className="mt-6 text-base leading-relaxed text-[#9ba9c3]">The updated adapter supports calendar search, edits, recurring series and occurrences, all-day events, and device reminders. An event is confirmed only after the service reads it back from Proton. If a write cannot be verified, check Proton before trying again.</p>
      <a className="mt-8 inline-block rounded-lg bg-[#6d58e8] px-5 py-3 text-base font-medium text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white" href="https://calendar.proton.me" target="_blank" rel="noreferrer">Open Proton Calendar</a>
    </div>
  </main>;
}
