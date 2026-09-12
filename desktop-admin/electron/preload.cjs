const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("x402Desktop", {
  platform: process.platform,
  isElectron: true,
});
