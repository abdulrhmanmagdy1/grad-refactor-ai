# recipes

A small recipe box. Recipes are plain text files with the extension `.recipe`, all kept in
one folder:

```text
# Pancakes
serves 4

ingredients:
200 g | flour
1 1/2 cups | milk
2 | eggs

steps:
Whisk everything together.
Fry ladlefuls in a hot pan.
```

An ingredient line is `<quantity> [unit] | <name>`. Quantities are whole numbers, decimals
or fractions (`1/2`, `1 1/2`); a line without a unit counts pieces.

- `load_folder` reads every recipe in a folder.
- `scale` rewrites a recipe for another number of servings; pieces are rounded up to whole
  ones.
- Units convert within mass (g, kg), volume (ml, l, tsp = 5 ml, tbsp = 15 ml,
  cup = 240 ml) and pieces, never between them.
- `shopping_list` turns a meal plan (recipe name to servings) into one list, adding up the
  same ingredient across recipes.
