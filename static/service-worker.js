/* Maareeye Personal Plan Web Push Service Worker */
self.addEventListener('push', function (event) {
  let data = {};
  try { data = event.data ? event.data.json() : {}; }
  catch (e) { data = { body: event.data ? event.data.text() : '' }; }

  const title = data.title || 'Maareeye — Reminder';
  const options = {
    body: data.body || 'Waxaad leedahay qorshe kuu baahan fiiro gaar ah.',
    icon: '/static/images/sooyaal-logo.png',
    badge: '/static/images/sooyaal-logo.png',
    tag: data.tag || 'maareeye-plan-reminder',
    renotify: true,
    data: { url: data.url || '/plan/' }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || '/plan/', self.location.origin).href;
  event.waitUntil((async function () {
    const windows = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      if (client.url.startsWith(self.location.origin) && 'focus' in client) {
        await client.focus();
        if ('navigate' in client) await client.navigate(target);
        return;
      }
    }
    if (clients.openWindow) await clients.openWindow(target);
  })());
});
