const express = require("express");
const router = express.Router();

const {
  createJob,
  getMyJobs,
  getAllJobs,
  updateJob,     // ✅ ADDED
  closeJob,      // ✅ ADDED
} = require("../controllers/jobController");

const { protect } = require("../middleware/authMiddleware");

// Recruiter posts a job
router.post("/", protect, createJob);

// Recruiter gets their own jobs
router.get("/my", protect, getMyJobs);

// Public route - Candidates see all active jobs
router.get("/", getAllJobs);

// ✅ Update a job (Recruiter only)
router.put("/:id", protect, updateJob);

// ✅ Close a job (Recruiter only)
router.patch("/:id/close", protect, closeJob);

module.exports = router;
