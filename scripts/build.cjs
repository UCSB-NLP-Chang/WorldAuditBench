const esbuild = require("esbuild");
esbuild.buildSync({
  entryPoints: ["src/app.jsx"],
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2020"],
  external: ["./manrope-latin.woff2"],
  outfile: "assets/app.js",
  define: { "process.env.NODE_ENV": '"production"' },
  legalComments: "linked",
});
console.log("Built assets/app.js and assets/app.css");
