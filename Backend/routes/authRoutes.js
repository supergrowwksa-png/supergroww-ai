const express = require("express");
const router = express.Router();

const {
  sendOtp,
  signup,
  login,
} = require("../controllers/authController");

const { protect } = require("../middleware/authMiddleware");
const { getMe } = require("../controllers/authController");

// Public auth routes
router.get("/me", protect, getMe);
router.post("/send-otp", sendOtp);
router.post("/signup", signup);
router.post("/login", login);

module.exports = router;
