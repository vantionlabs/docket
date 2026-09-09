import * as path from "node:path";

const DEFAULT_PACKAGE_PREFIXES = [
  "apps/server",
  "apps/web",
  "packages/database",
  "packages/domain",
];

function isExternal(name) {
  return isScoped(name) || isExternalModule(name);
}

const scopedRegExp = /^@[^/]+\/[^/]+/;
function isScoped(name) {
  return scopedRegExp.test(name);
}

const externalModuleRegExp = /^\w/;
function isExternalModule(name) {
  return externalModuleRegExp.test(name);
}

function getRelativePathDepth(importPath) {
  if (!importPath.startsWith(".")) return 0;
  const parts = importPath.split("/");
  let depth = 0;
  for (const part of parts) {
    if (part === "..") {
      depth++;
    } else if (part !== ".") {
      break;
    }
  }
  return depth;
}

const rule = {
  meta: {
    type: "suggestion",
    docs: {
      description:
        "Prevent relative imports going up more than one level (../../) inside a workspace package",
    },
    fixable: "code",
    schema: [
      {
        type: "object",
        properties: {
          packagePrefixes: {
            type: "array",
            items: { type: "string" },
          },
        },
        additionalProperties: false,
      },
    ],
  },
  create(context) {
    const cwd = process.cwd();
    const packagePrefixes = context.options?.[0]?.packagePrefixes ?? DEFAULT_PACKAGE_PREFIXES;

    function findPrefix(filename) {
      const relativeFilePath = path.relative(cwd, filename);
      return (
        packagePrefixes.find((prefix) => relativeFilePath.startsWith(prefix + path.sep)) ?? null
      );
    }

    function assertNoDeepRelativeImport(node, importPath, sourceNode) {
      if (typeof importPath !== "string" || isExternal(importPath)) return;

      const fileName = context.filename;
      const prefix = findPrefix(fileName);
      if (!prefix) return;

      if (getRelativePathDepth(importPath) <= 1) return;

      context.report({
        node,
        message:
          `Relative import "${importPath}" goes up more than one level. Use the "#src/..." subpath import instead.`,
        fix(fixer) {
          const srcRoot = path.join(cwd, prefix, "src");
          const absoluteImportPath = path.resolve(
            path.dirname(fileName),
            importPath,
          );

          const relativeToSrc = path.relative(srcRoot, absoluteImportPath);
          if (
            relativeToSrc.startsWith("..")
            || path.isAbsolute(relativeToSrc)
          ) {
            return null;
          }

          // `@/*` maps to the package's own `src`, per tsconfig.base.json and
          // the matching vitest alias.
          const aliased = `@/${relativeToSrc.replace(/\\/g, "/")}`;

          return fixer.replaceTextRange(sourceNode.range, `"${aliased}"`);
        },
      });
    }

    return {
      ImportDeclaration(node) {
        if (node.importKind === "type") return;
        assertNoDeepRelativeImport(node, node.source.value, node.source);
      },

      CallExpression(node) {
        const firstArg = node.arguments[0];
        if (
          node.callee.type === "Identifier"
          && node.callee.name === "require"
          && node.arguments.length > 0
          && firstArg?.type === "Literal"
          && typeof firstArg.value === "string"
        ) {
          assertNoDeepRelativeImport(node, firstArg.value, firstArg);
        } else if (
          node.callee.type === "ImportExpression"
          && node.arguments.length > 0
          && firstArg?.type === "Literal"
          && typeof firstArg.value === "string"
        ) {
          assertNoDeepRelativeImport(node, firstArg.value, firstArg);
        }
      },
    };
  },
};

export default rule;
