---
sidebar_position: 3
---

# Layer Editing

In GOAT, you can **create your own layers** and **edit features directly on the map**. This allows you to digitize new data, add attributes, and modify existing features without leaving the map view.

## Create Layer

<div class="step">
  <div class="step-number">1</div>
  <div class="content">Click on <code>+ Add Layer</code> in the left panel and select <code>Create Layer</code>.</div>
</div>

<div class="step">
  <div class="step-number">2</div>
  <div class="content">Enter a <b>Layer name</b> and select the <b>Geometry type</b>: <code>Point</code>, <code>Line</code>, <code>Polygon</code>, or <code>Table</code>. Click <code>Next</code> to continue.</div>
</div>

<div class="step">
  <div class="step-number">3</div>
  <div class="content">In the <b>Define Fields</b> step, you will see a default <code>name</code> field. Click <code>+ Add field</code> to add more fields. For each field, enter a <b>field name</b> and select its <b>Field type</b>: <code>Text</code> or <code>Number</code>. To remove a field, click the <code>—</code> icon next to it. Click <code>Create Layer</code> when done.</div>
</div>

## Edit Features

Once a layer is created, you can add and edit features directly on the map.

<div class="step">
  <div class="step-number">1</div>
  <div class="content">Click the <img src={require('/img/icons/3dots.png').default} alt="Options" style={{ maxHeight: "20px", maxWidth: "20px", objectFit: "cover"}}/> <code>more options</code> icon next to your layer and select <code>Edit features</code> to <strong>enter edit mode</strong>.</div>
</div>

<div class="step">
  <div class="step-number">2</div>
  <div class="content">Use the <strong>editing toolbar</strong> at the bottom of the map: click <code>+</code> to <strong>add a new feature</strong> and click on the map to draw the geometry. The <b>Feature Attributes</b> panel opens on the right — <strong>fill in the attribute values</strong> and click <code>Done</code>.</div>
</div>

<div class="step">
  <div class="step-number">3</div>
  <div class="content">When you are ready, click <code>Save</code> in the bottom bar to <strong>save your changes</strong>, or <code>Discard</code> to cancel them. The bar also shows the number of <strong>pending changes</strong>.</div>
</div>

## View Data

**View Data** lets you see and edit your layer data as a table. Open it from the layer's <code>more options</code> menu to manage fields, edit attribute values directly in the table, or enter edit mode to add and modify features on the map.

<div class="step">
  <div class="step-number">1</div>
  <div class="content">Click the <img src={require('/img/icons/3dots.png').default} alt="Options" style={{ maxHeight: "20px", maxWidth: "20px", objectFit: "cover"}}/> <code>more options</code> icon next to your layer and select <code>View Data</code>.</div>
</div>

<div class="step">
  <div class="step-number">2</div>
  <div class="content">Click <code>+ Add field</code> to open the <b>Edit fields</b> dialog. Add a new field by entering a <b>field name</b> and selecting its <b>Field type</b>. To remove a field, click the <code>—</code> icon next to it. Click <code>Save</code> when done.</div>
</div>

<div class="step">
  <div class="step-number">3</div>
  <div class="content">Click <code>Edit features</code> in the table toolbar to enter edit mode. You can <strong>click directly on a cell</strong> in the table to edit attribute values inline, use the <strong>pointer</strong> on the map to select an existing feature and update its attributes in the <b>Feature attributes</b> panel, or use <code>+</code> to draw a new feature. Click <code>Save</code> or <code>Discard</code> when done.</div>
</div>
