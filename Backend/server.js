const express = require("express");
const dotenv = require("dotenv");
const cors = require("cors");
const path = require("path");
const connectDB = require("./config/db");

const authRoutes = require("./routes/authRoutes");
const userRoutes = require("./routes/userRoutes");
const jobRoutes = require("./routes/jobRoutes"); // ✅ ADDED

// Load environment variables
dotenv.config();

// Connect to MongoDB
connectDB();

const app = express();

// --- Middleware ---
app.use(cors());
app.use(express.json());

// ✅ SERVE UPLOADED FILES (CRITICAL FIX)
app.use("/uploads", express.static(path.join(__dirname, "uploads")));

// --- Routes ---
app.use("/api/auth", authRoutes);
app.use("/api/user", userRoutes);
app.use("/api/jobs", jobRoutes); // ✅ ADDED

// Health check route
app.get("/", (req, res) => {
  res.send("SuperGroww API is running successfully...");
});

// --- Server Start ---
const PORT = process.env.PORT || 5000;

app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});

const interviewRoutes = require("./routes/interviewRoutes");

app.use("/api/interview", interviewRoutes);