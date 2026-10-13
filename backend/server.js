const express = require("express");

const app = express();

app.use(express.json());

app.get("/", (req, res) => {
  res.send("Buff Bison Construction backend is running");
});

app.get("/api/projects", (req, res) => {
  res.json([
    {
      projectNumber: "BBC-001",
      projectName: "Kitchen Remodel",
      client: "John Smith",
      status: "In Progress"
    }
  ]);
});

app.listen(3000, () => {
  console.log("Server running on port 3000");
});