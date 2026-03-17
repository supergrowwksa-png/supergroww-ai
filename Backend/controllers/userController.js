const User = require("../models/User");
const { deleteFileIfExists } = require("../middleware/uploadMiddleware");

/**
 * =========================
 * GET MY PROFILE
 * =========================
 */
exports.getMyProfile = async (req, res) => {
  try {
    const user = await User.findById(req.user._id).select("-password");

    if (!user) {
      return res.status(404).json({ message: "User not found" });
    }

    res.status(200).json({ success: true, user });
  } catch (error) {
    res.status(500).json({
      message: "Failed to fetch profile",
      error: error.message,
    });
  }
};

/**
 * =========================
 * SAVE BASIC DETAILS (FIRST LOGIN)
 * =========================
 * PUT /api/user/basic-details
 */
exports.saveBasicDetails = async (req, res) => {
  try {
    const allowedFields = [
      // Common
      "profileType",
      "city",
      "extraInfo",

      // Student
      "educationStatus",
      "college",
      "degree",
      "specialization",
      "graduationYear",

      // Professional
      "jobStatus",
      "experience",
      "company",
      "jobRole",
    ];

    const updateData = {};

    allowedFields.forEach((field) => {
      if (req.body[field] !== undefined) {
        updateData[field] = req.body[field];
      }
    });

    updateData.profileCompleted = true;

    const updatedUser = await User.findByIdAndUpdate(
      req.user._id,
      { $set: updateData },
      { new: true, runValidators: true }
    ).select("-password");

    res.status(200).json({
      success: true,
      message: "Basic details saved successfully",
      user: updatedUser,
    });
  } catch (error) {
    res.status(500).json({
      message: "Failed to save basic details",
      error: error.message,
    });
  }
};

/**
 * =========================
 * UPDATE PROFILE (EDIT PAGE)
 * =========================
 * PATCH /api/user/profile
 */
exports.updateBasicProfile = async (req, res) => {
  try {
    const allowedFields = [
      // Common
      "name",
      "surname",
      "country",
      "city",
      "profileType",
      "extraInfo",
      "skills",

      // Student
      "educationStatus",
      "college",
      "degree",
      "specialization",
      "graduationYear",

      // Professional
      "jobStatus",
      "experience",
      "company",
      "jobRole",
    ];

    const updateData = {};

    allowedFields.forEach((field) => {
      if (req.body[field] !== undefined) {
        updateData[field] = req.body[field];
      }
    });

    const updatedUser = await User.findByIdAndUpdate(
      req.user._id,
      { $set: updateData },
      { new: true, runValidators: true }
    ).select("-password");

    res.status(200).json({
      success: true,
      message: "Profile updated successfully",
      user: updatedUser,
    });
  } catch (error) {
    res.status(500).json({
      message: "Failed to update profile",
      error: error.message,
    });
  }
};

/**
 * =========================
 * UPDATE LINKS
 * =========================
 */
exports.updateLinks = async (req, res) => {
  try {
    const updateData = {};

    if (req.body.linkedinUrl !== undefined) {
      updateData.linkedinUrl = req.body.linkedinUrl;
    }

    if (req.body.githubUrl !== undefined) {
      updateData.githubUrl = req.body.githubUrl;
    }

    const updatedUser = await User.findByIdAndUpdate(
      req.user._id,
      { $set: updateData },
      { new: true, runValidators: true }
    ).select("-password");

    res.status(200).json({
      success: true,
      message: "Links updated successfully",
      user: updatedUser,
    });
  } catch (error) {
    res.status(500).json({
      message: "Failed to update links",
      error: error.message,
    });
  }
};

/**
 * =========================
 * UPLOAD RESUME
 * =========================
 */
exports.uploadResume = async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ message: "No resume uploaded" });
    }

    const user = await User.findById(req.user._id);
    if (!user) {
      return res.status(404).json({ message: "User not found" });
    }

    if (user.resume) {
      deleteFileIfExists(user.resume);
    }

    user.resume = "/uploads/resume/" + req.file.filename;
    await user.save();

    const updatedUser = user.toObject();
    delete updatedUser.password;

    res.status(200).json({
      success: true,
      message: "Resume uploaded successfully",
      user: updatedUser,
    });
  } catch (error) {
    res.status(500).json({
      message: "Resume upload failed",
      error: error.message,
    });
  }
};

/**
 * =========================
 * UPLOAD PROFILE PHOTO
 * =========================
 */
exports.uploadProfilePhoto = async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ message: "No profile photo uploaded" });
    }

    const user = await User.findById(req.user._id);
    if (!user) {
      return res.status(404).json({ message: "User not found" });
    }

    if (user.profilePhoto) {
      deleteFileIfExists(user.profilePhoto);
    }

    user.profilePhoto = "/uploads/profile/" + req.file.filename;
    await user.save();

    const updatedUser = user.toObject();
    delete updatedUser.password;

    res.status(200).json({
      success: true,
      message: "Profile photo updated successfully",
      user: updatedUser,
    });
  } catch (error) {
    res.status(500).json({
      message: "Profile photo upload failed",
      error: error.message,
    });
  }
};
