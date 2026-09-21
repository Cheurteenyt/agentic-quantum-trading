const net = require("net");

const targetHost = process.argv[2];
const mappings = process.argv.slice(3).map((item) => {
  const [listen, target] = item.split(":").map((value) => Number.parseInt(value, 10));
  return { listen, target };
});

if (!targetHost || mappings.length === 0 || mappings.some((item) => !item.listen || !item.target)) {
  console.error("Usage: node scripts/dev_local_wsl_proxy.js <wsl-ip> <listenPort:targetPort> [...]");
  process.exit(2);
}

for (const { listen, target } of mappings) {
  const server = net.createServer((client) => {
    const upstream = net.connect(target, targetHost);
    client.pipe(upstream);
    upstream.pipe(client);
    const closeBoth = () => {
      client.destroy();
      upstream.destroy();
    };
    client.on("error", closeBoth);
    upstream.on("error", closeBoth);
  });

  server.listen(listen, "127.0.0.1", () => {
    console.log(`proxy 127.0.0.1:${listen} -> ${targetHost}:${target}`);
  });

  server.on("error", (error) => {
    console.error(`proxy failed on ${listen}: ${error.message}`);
    process.exitCode = 1;
  });
}
