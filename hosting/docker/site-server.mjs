// Container entry point for tests/model-bench/server.mjs, which runs unchanged.
//
// That server listens on 127.0.0.1, which is what you want on a laptop but unreachable from outside a
// container, so a published port would never connect. This file makes the server it creates listen on every
// interface instead. Everything else - the routes, the file map, the /api forwarding, PORT and BACKEND_URL -
// still comes from server.mjs itself, so there is one copy of that logic and it cannot drift.
import http from "node:http";

const listen = http.Server.prototype.listen;
http.Server.prototype.listen = function (port, host, ...rest) {
  return listen.call(this, port, "0.0.0.0", ...rest);
};

await import("../../tests/model-bench/server.mjs");
