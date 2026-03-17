const express = require("express");
const router = express.Router();

const { startInterview } = require("../controllers/interviewController");
const { protect } = require("../middleware/authMiddleware");

// Candidate starts AI interview
router.post("/start/:jobId", protect, startInterview);

module.exports = router;