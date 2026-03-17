const express = require("express");
const router = express.Router();

const { protect } = require("../middleware/authMiddleware");
const upload = require("../middleware/uploadMiddleware");

const {
  getMyProfile,
  updateBasicProfile,
  updateLinks,
  uploadResume,
  uploadProfilePhoto,
  saveBasicDetails,
} = require("../controllers/userController");

/**
 * =========================
 * PROFILE CORE
 * =========================
 */

// Get logged-in user's profile
router.get("/me", protect, getMyProfile);

// Save basic details (FIRST LOGIN ONLY)
router.put("/basic-details", protect, saveBasicDetails);

// Update basic profile (edit later)
router.patch("/profile", protect, updateBasicProfile);

/**
 * =========================
 * PROFILE SECTIONS
 * =========================
 */

// Update links
router.patch("/links", protect, updateLinks);

// Upload resume
router.post(
  "/resume",
  protect,
  upload.single("resume"),
  uploadResume
);

// Upload profile photo
router.post(
  "/profile-photo",
  protect,
  upload.single("profilePhoto"),
  uploadProfilePhoto
);

module.exports = router;
